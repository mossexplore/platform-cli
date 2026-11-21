import { appendFile, mkdir, rename, stat } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

const loggerName = 'wiserec-cli-keepalive'
const format = 'WiseRec keepalive: %o'
const maxSegmentBytes = 256 * 1024
const maxQueuedRecords = 128

const levels = new Map([
  ['scheduler_started', 'info'],
  ['keepalive_confirmed', 'info'],
  ['keepalive_unconfirmed', 'warn'],
  ['session_expired', 'warn'],
  ['cli_timeout', 'warn'],
  ['cli_failed', 'warn'],
  ['legacy_worker', 'warn'],
  ['host_unavailable', 'warn'],
])
const failureReasons = new Set([
  'cli_access_failed', 'incompatible_cli', 'invalid_request', 'invalid_response', 'invalid_timeout',
  'invocation_failed', 'local_error', 'missing_cli', 'unexpected_error',
])
const requestIDFormat = /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i

export function failureReason(value) {
  return failureReasons.has(value) ? value : 'unexpected_error'
}

function safeField(value, limit) {
  return typeof value === 'string' && value.length > 0 && [...value].length <= limit &&
    !/\p{Cc}/u.test(value)
}

function logFields(event, source) {
  const fields = { event }
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

function logWriter(directory, limit, onFailure) {
  const path = join(directory, `keepalive-${process.pid}.jsonl`)
  const previous = join(directory, `keepalive-${process.pid}.previous.jsonl`)
  let size
  let queued = 0
  let tail = Promise.resolve()
  let failed = false

  function write(record) {
    if (queued >= maxQueuedRecords || failed) return
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
  if (directory && typeof service?.exporter === 'function') {
    writer = logWriter(directory, limit, () => logger?.warn('WiseRec keepalive: log_write_failed'))
    dispose = ctx.logger.exporter({
      levels: { default: -1, [loggerName]: 2 },
      export(message) {
        if (message.name !== loggerName || message.args[0] !== format) return
        const source = message.args[1]
        const level = levels.get(source?.event)
        if (!level || message.type !== level) return
        const { event, sessionID, env, requestID, reason } = logFields(source.event, source)
        writer.write({
          time: beijingTime(message.ts ?? Date.now()), level, event,
          session_id: sessionID, env, request_id: requestID, reason,
        })
      },
    })
  }
  return {
    record(event, details = {}) {
      const level = levels.get(event)
      if (level) logger?.[level](format, logFields(event, details))
    },
    async close() {
      await dispose?.()
      await writer?.drain()
    },
  }
}
