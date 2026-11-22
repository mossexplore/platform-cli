import { randomUUID } from 'node:crypto'
import { appendFile, lstat, mkdir, readdir, rename, stat, unlink } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

const loggerName = 'wiserec-cli-keepalive'
const format = 'WiseRec keepalive: %o'
const maxSegmentBytes = 256 * 1024
const maxQueuedRecords = 128
const cleanupInterval = 24 * 60 * 60 * 1000
const maxLogAge = 7 * cleanupInterval
const maxDirectoryBytes = 10 * 1024 * 1024
const logFilename = /^(keepalive-([1-9]\d*)(?:\.previous)?\.jsonl)(?:\.cleanup-([1-9]\d*)-[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12})?$/
const activeClaims = new Set()

const levels = new Map([
  ['scheduler_started', 'info'],
  ['keepalive_confirmed', 'info'],
  ['keepalive_unconfirmed', 'warn'],
  ['session_expired', 'warn'],
  ['cli_timeout', 'warn'],
  ['cli_failed', 'warn'],
  ['legacy_worker', 'warn'],
  ['host_unavailable', 'warn'],
  ['log_cleanup_completed', 'info'],
  ['log_cleanup_failed', 'warn'],
])
const failureReasons = new Set([
  'cli_access_failed', 'incompatible_cli', 'invalid_request', 'invalid_response', 'invalid_timeout',
  'invocation_failed', 'local_error', 'missing_cli', 'unexpected_error',
])
const requestIDFormat = /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i
const cleanupReasons = new Set(['scan_failed', 'delete_failed'])

export function failureReason(value) {
  return failureReasons.has(value) ? value : 'unexpected_error'
}

function safeField(value, limit) {
  return typeof value === 'string' && value.length > 0 && [...value].length <= limit &&
    !/\p{Cc}/u.test(value)
}

function isCleanupEvent(event) {
  return event === 'log_cleanup_completed' || event === 'log_cleanup_failed'
}

function logFields(event, source) {
  const fields = { event }
  if (isCleanupEvent(event)) {
    if (source.trigger === 'startup' || source.trigger === 'periodic') fields.trigger = source.trigger
    for (const key of ['expired_deleted', 'capacity_deleted']) {
      if (Number.isSafeInteger(source[key]) && source[key] >= 0) fields[key] = source[key]
    }
    if (Number.isFinite(source.deleted_kb) && source.deleted_kb >= 0) fields.deleted_kb = source.deleted_kb
    if (event === 'log_cleanup_failed' && cleanupReasons.has(source.reason)) fields.reason = source.reason
    return fields
  }
  if (safeField(source.sessionID, 256)) fields.sessionID = source.sessionID
  if (safeField(source.env, 256)) fields.env = source.env
  if (typeof source.requestID === 'string' && requestIDFormat.test(source.requestID)) {
    fields.requestID = source.requestID
  }
  if (event === 'cli_failed') {
    fields.reason = failureReason(source.reason)
  }
  return fields
}

function windowsLogDirectory() {
  const root = process.env.LOCALAPPDATA
  if (process.platform === 'win32' && root && isAbsolute(root)) {
    return join(root, 'WiseRec', 'dsh-plugins', 'wiserec-cli', 'logs')
  }
}

function beijingTime(timestamp) {
  return new Date(timestamp + 8 * 60 * 60 * 1000).toISOString().slice(0, 19).replace('T', ' ')
}

async function ignoreMissing(operation) {
  try {
    return await operation()
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
}

function hostExited(pid) {
  try {
    process.kill(pid, 0)
  } catch (error) {
    return error.code === 'ESRCH'
  }
  return false
}

export async function cleanupKeepaliveLogs(directory, {
  now = Date.now(), maxBytes = maxDirectoryBytes, isHostExited = hostExited,
} = {}) {
  const result = { expiredDeleted: 0, capacityDeleted: 0, deletedBytes: 0 }
  let names
  try {
    const root = await ignoreMissing(() => lstat(directory))
    if (!root) return result
    if (!root.isDirectory()) return { ...result, reason: 'scan_failed' }
    names = await ignoreMissing(() => readdir(directory))
  } catch {
    return { ...result, reason: 'scan_failed' }
  }
  if (!names) return result

  let totalBytes = 0
  const files = []
  for (const name of names) {
    const match = logFilename.exec(name)
    if (!match) continue
    const [, baseName, originalPID, claimedBy] = match
    const pid = Number(originalPID)
    const owner = Number(claimedBy ?? 0)
    if (pid > 0x7fffffff || owner > 0x7fffffff) continue
    const path = join(directory, name)
    try {
      const info = await ignoreMissing(() => lstat(path))
      if (!info?.isFile()) continue
      totalBytes += info.size
      files.push({ path, baseName, pid, owner, info })
    } catch {
      result.reason = 'scan_failed'
    }
  }

  files.sort((a, b) => a.info.mtimeMs - b.info.mtimeMs || a.path.localeCompare(b.path))
  for (const { path, baseName, pid, owner, info } of files) {
    const expired = now - info.mtimeMs >= maxLogAge
    if (!expired && totalBytes <= maxBytes) break
    if (pid === process.pid) continue
    try {
      if (activeClaims.has(path) || (owner && owner !== process.pid && !isHostExited(owner))) continue
      if (!isHostExited(pid)) continue
      // Another host may have rotated or removed this file during the scan.
      const current = await ignoreMissing(() => lstat(path))
      if (!current?.isFile()) {
        totalBytes -= info.size
        continue
      }
      totalBytes += current.size - info.size
      if (current.dev !== info.dev || current.ino !== info.ino || current.ctimeMs !== info.ctimeMs ||
          current.mtimeMs !== info.mtimeMs || current.size !== info.size) continue
      // Concurrent unlinks can both report success. Only one sweep can move the original.
      const claim = join(directory, `${baseName}.cleanup-${process.pid}-${randomUUID()}`)
      activeClaims.add(claim)
      let deleted
      try {
        deleted = await ignoreMissing(async () => {
          await rename(path, claim)
          await unlink(claim)
          return true
        })
      } finally {
        activeClaims.delete(claim)
      }
      totalBytes -= current.size
      if (!deleted) continue
      if (expired) result.expiredDeleted++
      else result.capacityDeleted++
      result.deletedBytes += current.size
    } catch {
      result.reason ??= 'delete_failed'
    }
  }
  return result
}

function startLogCleanup(directory, onResult) {
  let pending
  function sweep(trigger) {
    if (pending) return
    pending = cleanupKeepaliveLogs(directory)
      .then(result => onResult(trigger, result))
      .finally(() => { pending = undefined })
  }
  sweep('startup')
  const timer = setInterval(() => sweep('periodic'), cleanupInterval)
  timer.unref()
  return async () => {
    clearInterval(timer)
    await pending
  }
}

function logWriter(directory, limit, onFailure) {
  const path = join(directory, `keepalive-${process.pid}.jsonl`)
  const previous = join(directory, `keepalive-${process.pid}.previous.jsonl`)
  let size
  let queued = 0
  let tail = Promise.resolve()
  let failed = false

  function write(record) {
    if (failed || (queued >= maxQueuedRecords && !isCleanupEvent(record.event))) return
    const line = JSON.stringify(record) + '\n'
    const bytes = Buffer.byteLength(line)
    queued++
    tail = tail.then(async () => {
      if (failed) return
      if (size === undefined) {
        await mkdir(directory, { recursive: true, mode: 0o700 })
        try {
          size = (await stat(path)).size
        } catch (error) {
          if (error.code !== 'ENOENT') throw error
          size = 0
        }
      }
      if (size > 0 && size + bytes > limit) {
        await rename(path, previous)
        size = 0
      }
      await appendFile(path, line, { mode: 0o600 })
      size += bytes
    }).catch(() => {
      failed = true
      onFailure()
    }).finally(() => { queued-- })
  }

  return { write, drain: () => tail }
}

export function createKeepaliveLog(ctx, { directory = windowsLogDirectory(), limit = maxSegmentBytes } = {}) {
  const service = ctx.logger
  const logger = typeof service === 'function' ? ctx.logger(loggerName) : undefined
  let writer
  let dispose
  let stopCleanup

  function record(event, details = {}) {
    const level = levels.get(event)
    if (level) logger?.[level](format, logFields(event, details))
  }

  if (directory && typeof service?.exporter === 'function') {
    writer = logWriter(directory, limit, () => logger?.warn('WiseRec keepalive: log_write_failed'))
    dispose = ctx.logger.exporter({
      levels: { default: -1, [loggerName]: 2 },
      export(message) {
        if (message.name !== loggerName || message.args[0] !== format) return
        const source = message.args[1]
        const level = levels.get(source?.event)
        if (!level || message.type !== level) return
        const { event, sessionID, env, requestID, reason, ...cleanup } = logFields(source.event, source)
        writer.write({
          time: beijingTime(message.ts ?? Date.now()), level, event,
          session_id: sessionID, env, request_id: requestID, ...cleanup, reason,
        })
      },
    })
    stopCleanup = startLogCleanup(directory, (trigger, result) => {
      record(result.reason ? 'log_cleanup_failed' : 'log_cleanup_completed', {
        trigger, expired_deleted: result.expiredDeleted, capacity_deleted: result.capacityDeleted,
        deleted_kb: Number((result.deletedBytes / 1024).toFixed(2)), reason: result.reason,
      })
    })
  }
  return {
    record,
    async close() {
      await stopCleanup?.()
      await dispose?.()
      await writer?.drain()
    },
  }
}
