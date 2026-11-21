import { randomUUID } from 'node:crypto'
import { isAbsolute } from 'node:path'
import { createRunner } from './runner.js'
import { createKeepaliveLog, failureReason } from './logging.js'

export const name = 'wiserec-cli-keepalive'
export const inject = ['agents']

function configuration(input = {}) {
  const values = {
    enabled: true, mlPath: '', pollSeconds: 120, idleWindowMinutes: 120, timeoutSeconds: 0, ...input,
  }
  if (typeof values.enabled !== 'boolean' || typeof values.mlPath !== 'string' ||
      (values.mlPath && !isAbsolute(values.mlPath)) ||
      !Number.isInteger(values.pollSeconds) || values.pollSeconds < 60 || values.pollSeconds > 180 ||
      !Number.isInteger(values.idleWindowMinutes) || values.idleWindowMinutes < 1 ||
      !Number.isInteger(values.timeoutSeconds) || values.timeoutSeconds < 0 || values.timeoutSeconds > 300) {
    throw new Error('invalid WiseRec keepalive configuration')
  }
  return values
}

const outcomes = new Map([
  ['confirmed', 'keepalive_confirmed'],
  ['retrying', 'keepalive_unconfirmed'],
  ['expired', 'session_expired'],
  ['legacy_worker', 'legacy_worker'],
  ['invalid_request', 'cli_failed'],
  ['local_error', 'cli_failed'],
])
const warningInterval = 5 * 60_000

export function startScheduler(ctx, config, run = createRunner(config), clock = Date.now, log = () => {}) {
  const hostID = randomUUID()
  const sessions = new Map()
  const pendingRelease = new Set()
  const idleLimit = config.idleWindowMinutes * 60_000
  const interval = config.pollSeconds * 1000
  let inFlight
  let closed = false

  function report(record, event, details) {
    if (event !== 'keepalive_confirmed') {
      const key = JSON.stringify([event, details.env, event === 'cli_failed' ? details.reason : undefined])
      const now = clock()
      const last = record.warnings.get(key) ?? -Infinity
      if (now - last < warningInterval) return
      record.warnings.set(key, now)
    }
    log(event, details)
  }

  function refresh(agent, status) {
    const id = agent?.session?.header?.id
    if (!id || typeof id !== 'string') return
    const existing = sessions.get(id)
    if (existing?.agent !== agent && existing) retire(id, existing)
    const record = sessions.get(id) ?? { agent, lastTick: -Infinity, registered: false, warnings: new Map() }
    record.activity = clock()
    record.busy = (status ?? agent.status) === 'running'
    sessions.set(id, record)
    queueMicrotask(cycle)
  }

  function retire(id, record) {
    if (inFlight?.id === id && inFlight.action === 'tick') inFlight.controller.abort()
    if (record.registered || inFlight?.id === id) pendingRelease.add(id)
    record.registered = false
  }

  function dispose(agent) {
    const id = agent?.session?.header?.id
    const record = sessions.get(id)
    if (!record || record.agent !== agent) return
    retire(id, record)
    sessions.delete(id)
    queueMicrotask(cycle)
  }

  function cycle() {
    if (inFlight || closed) return
    const now = clock()
    let candidate
    for (const [id, record] of sessions) {
      if (!record.busy && now - record.activity >= idleLimit) {
        if (record.registered) retire(id, record)
        continue
      }
      if (now - record.lastTick >= interval &&
          (!candidate || record.lastTick < candidate[1].lastTick)) {
        candidate = [id, record]
      }
    }
    const release = pendingRelease.values().next().value
    if (release !== undefined) {
      pendingRelease.delete(release)
      invoke('release', release)
    } else if (candidate) {
      const [id, record] = candidate
      record.lastTick = now
      invoke('tick', id, record)
    }
  }

  function invoke(action, id, record) {
    const controller = new AbortController()
    const invocation = { id, action, controller }
    inFlight = invocation
    invocation.done = (async () => {
      try {
        const result = await run(action, hostID, id, controller.signal)
        if (!record || controller.signal.aborted) return
        if (result.state !== 'unknown_session') record.registered = true
        const event = outcomes.get(result.state)
        if (event && (result.state !== 'expired' || result.requestID)) {
          report(record, event, {
            sessionID: id, env: result.env, requestID: result.requestID, reason: result.state,
          })
        }
      } catch (error) {
        if (record && !controller.signal.aborted) {
          const event = error?.message === 'timeout' ? 'cli_timeout' : 'cli_failed'
          report(record, event, { sessionID: id, reason: failureReason(error?.message) })
        }
      } finally {
        inFlight = undefined
        if (!closed) queueMicrotask(cycle)
      }
    })()
  }

  const listeners = [
    ctx.on('agent/created', ({ agent }) => refresh(agent)),
    ctx.on('agent/session-start', ({ agent }) => refresh(agent)),
    ctx.on('agent/status', ({ agent, status }) => refresh(agent, status)),
    ctx.on('agent/disposed', ({ agent }) => dispose(agent)),
  ]
  for (const agent of ctx.agents.list()) refresh(agent)
  const timer = setInterval(cycle, interval)
  timer.unref()
  log('scheduler_started')
  return async () => {
    closed = true
    clearInterval(timer)
    for (const disposeListener of listeners) disposeListener()
    for (const [id, record] of sessions) retire(id, record)
    const active = inFlight
    active?.controller.abort()
    await active?.done
    const cleanup = AbortSignal.timeout(4000)
    for (const id of pendingRelease) {
      if (cleanup.aborted) break
      try {
        await run('release', hostID, id, cleanup)
      } catch {
        // The CLI also expires registrations when a host cannot release them.
      }
    }
  }
}

export function apply(ctx, rawConfig) {
  const config = configuration(rawConfig)
  if (!config.enabled) return
  const log = createKeepaliveLog(ctx)
  ctx.effect(() => {
    if (process.platform !== 'win32' && !config.mlPath) {
      log.record('cli_failed', { reason: 'missing_cli' })
      return log.close
    }
    if (typeof ctx.agents?.list !== 'function') {
      log.record('host_unavailable')
      return log.close
    }
    const stop = startScheduler(ctx, config, createRunner(config), Date.now, log.record)
    return async () => {
      try {
        await stop()
      } finally {
        await log.close()
      }
    }
  }, 'wiserec-cli keepalive')
}
