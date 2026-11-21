import { randomUUID } from 'node:crypto'
import { isAbsolute } from 'node:path'
import { createRunner } from './runner.js'

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

const reportable = new Set(['confirmed', 'retrying', 'expired', 'legacy_worker', 'local_error'])
const reasons = new Set(['cancelled', 'timeout', 'invocation_failed', 'missing_cli', 'incompatible_cli', 'invalid_timeout', 'invalid_response'])

export function startScheduler(ctx, config, run = createRunner(config), clock = Date.now) {
  const hostID = randomUUID()
  const sessions = new Map()
  const pendingRelease = new Set()
  const idleLimit = config.idleWindowMinutes * 60_000
  const interval = config.pollSeconds * 1000
  let inFlight
  let closed = false
  let lastWarning = -Infinity

  function report(error) {
    if (clock() - lastWarning < 5 * 60_000) return
    lastWarning = clock()
    const message = reasons.has(error?.message) ? error.message : 'local_error'
    ctx.logger?.warn(`WiseRec keepalive: ${message}`)
  }

  function refresh(agent, status) {
    const id = agent?.session?.header?.id
    if (!id || typeof id !== 'string') return
    const existing = sessions.get(id)
    if (existing?.agent !== agent && existing) retire(id, existing)
    const record = sessions.get(id) ?? { agent, lastTick: -Infinity, registered: false }
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
        if (record && !controller.signal.aborted && result.state !== 'unknown_session') record.registered = true
        if (reportable.has(result.state)) {
          ctx.logger?.info(`WiseRec keepalive: ${result.state}${result.requestID ? ` request_id=${result.requestID}` : ''}`)
        }
      } catch (error) {
        if (!controller.signal.aborted) report(error)
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
  if (process.platform !== 'win32' && !config.mlPath) {
    ctx.logger?.warn('WiseRec keepalive: configure an absolute mlPath for a local runtime check')
    return
  }
  if (typeof ctx.agents?.list !== 'function') {
    ctx.logger?.warn('WiseRec keepalive: host activity service is unavailable')
    return
  }
  ctx.effect(() => startScheduler(ctx, config), 'wiserec-cli keepalive')
}
