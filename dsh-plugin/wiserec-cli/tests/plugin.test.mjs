import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { startScheduler } from '../index.js'
import { createKeepaliveLog } from '../logging.js'
import { hostEnvironment } from '../runner.js'

function host(agents = []) {
  const events = new EventEmitter()
  const ctx = {
    agents: { list: () => agents },
    on(event, listener) {
      events.on(event, listener)
      return () => events.off(event, listener)
    },
  }
  return { ctx, emit: (event, agent, status) => events.emit(event, { agent, status }) }
}

const config = { idleWindowMinutes: 1, pollSeconds: 60 }
const agent = (id) => ({ session: { header: { id } }, status: 'idle' })

test('uses the host session identity and retires only that registration', async () => {
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host([a])
  const calls = []
  const stop = startScheduler(ctx, config, async (action, hostID, sessionID) => {
    calls.push({ action, hostID, sessionID })
    return { state: 'confirmed' }
  })
  try {
    emit('agent/created', b)
    await setImmediate()
    emit('agent/disposed', a)
    await setImmediate()
    assert.deepEqual(calls.map(({ action, sessionID }) => [action, sessionID]), [
      ['tick', 'session-a'], ['tick', 'session-b'], ['release', 'session-a'],
    ])
    assert.equal(new Set(calls.map(({ hostID }) => hostID)).size, 1)
  } finally {
    await stop()
  }
  assert.deepEqual(calls.at(-1).sessionID, 'session-b')
  assert.equal(calls.at(-1).action, 'release')
})

test('cancels a closing session before releasing it and does not overlap child calls', async () => {
  const a = agent('session-a')
  const { ctx, emit } = host([a])
  const calls = []
  let concurrent = 0
  const stop = startScheduler(ctx, config, async (action, _, id, signal) => {
    assert.equal(++concurrent, 1)
    calls.push([action, id])
    if (action === 'tick' && id === 'session-a') {
      await new Promise((resolve) => signal.addEventListener('abort', resolve, { once: true }))
      assert.equal(signal.aborted, true)
    }
    concurrent--
    return { state: 'confirmed' }
  })
  try {
    await setImmediate()
    emit('agent/created', agent('session-b'))
    emit('agent/disposed', a)
    await setImmediate()
    assert.deepEqual(calls, [
      ['tick', 'session-a'], ['release', 'session-a'], ['tick', 'session-b'],
    ])
  } finally {
    await stop()
  }
})

test('keeps idle owners bounded and resumes after host activity', async () => {
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host([a])
  const calls = []
  let now = 0
  const stop = startScheduler(ctx, config, async (action, _, id) => {
    calls.push([action, id])
    return { state: 'confirmed' }
  }, () => now)
  try {
    await setImmediate()
    now += 61_000
    emit('agent/created', b)
    await setImmediate()
    emit('agent/status', a, 'running')
    await setImmediate()
    assert.deepEqual(calls, [
      ['tick', 'session-a'], ['release', 'session-a'], ['tick', 'session-b'], ['tick', 'session-a'],
    ])
  } finally {
    await stop()
  }
})

test('removes inherited Windows case variants of shell context variables', () => {
  assert.deepEqual(hostEnvironment({
    dsh_shell: '1', DSH_SESSION_ID: 'old', ml_Session_Id: 'old', TEMP: 'kept',
  }), { TEMP: 'kept' })
})

test('logs actual results, suppresses repeated warnings, and never guesses a timeout target', async () => {
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host()
  const records = []
  let now = 0
  let result = { state: 'retrying', env: 'dev', requestID: 'a14b83d1-2f0a-481b-9e19-0a44ee8cf001' }
  const stop = startScheduler(ctx, { ...config, idleWindowMinutes: 120 }, async (action) => {
    if (action === 'release') return { state: 'released' }
    if (result instanceof Error) throw result
    return result
  }, () => now, (event, details) => records.push({ event, ...details }))
  async function activity(session, advance = 0) {
    now += advance
    emit('agent/status', session, 'running')
    await setImmediate()
  }
  try {
    await activity(a)
    await activity(a, 60_000)
    await activity(b)
    emit('agent/disposed', a)
    await setImmediate()
    result = new Error('timeout')
    await activity(b, 60_000)
    result = { state: 'expired', env: 'dev' }
    await activity(b, 60_000)
    result = { state: 'confirmed', env: 'uat', requestID: 'f85e2c07-2f0a-481b-9e19-0a44ee8cf002' }
    await activity(b, 60_000)

    assert.deepEqual(records.map(({ event }) => event), [
      'scheduler_started', 'keepalive_unconfirmed', 'keepalive_unconfirmed', 'cli_timeout', 'keepalive_confirmed',
    ])
    assert.equal(records[1].sessionID, 'session-a')
    assert.equal(records[2].sessionID, 'session-b')
    assert.equal(records[3].sessionID, 'session-b')
    assert.equal(records[3].env, undefined)
    assert.equal(records[3].requestID, undefined)
    assert.equal(records[4].env, 'uat')
    assert.equal(records[4].requestID, result.requestID)
  } finally {
    await stop()
  }
})

function loggingContext(timestamp) {
  const exporters = new Set()
  function logger(name) {
    const dispatch = (type) => (...args) => {
      for (const exporter of exporters) exporter.export({ name, type, ts: timestamp, args })
    }
    return { info: dispatch('info'), warn: dispatch('warn') }
  }
  logger.exporter = (exporter) => {
    exporters.add(exporter)
    return () => exporters.delete(exporter)
  }
  return { logger, exporters }
}

test('persists only allowlisted Cordis events with Beijing timestamps and rotates by PID', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-keepalive-'))
  const ctx = loggingContext(Date.parse('2026-11-22T18:00:00Z'))
  const log = createKeepaliveLog(ctx, { directory, limit: 280 })
  const logPath = join(directory, `keepalive-${process.pid}.jsonl`)
  try {
    log.record('scheduler_started')
    ctx.logger('unrelated').info('WiseRec keepalive: %o', { event: 'scheduler_started' })
    log.record('keepalive_confirmed', {
      sessionID: 'session-123', env: 'dev', requestID: 'a14b83d1-2f0a-481b-9e19-0a44ee8cf001',
      cookie: 'sensitive-value',
    })
    log.record('cli_timeout', { sessionID: 'session-123' })
    await log.close()
    assert.equal(ctx.exporters.size, 0)

    const previous = await readFile(join(directory, `keepalive-${process.pid}.previous.jsonl`), 'utf8')
    const current = await readFile(logPath, 'utf8')
    const lines = (previous + current).trim().split('\n').map(JSON.parse)
    assert.deepEqual(lines, [
      { time: '2026-11-23 02:00:00', level: 'info', event: 'scheduler_started' },
      {
        time: '2026-11-23 02:00:00', level: 'info', event: 'keepalive_confirmed',
        session_id: 'session-123', env: 'dev', request_id: 'a14b83d1-2f0a-481b-9e19-0a44ee8cf001',
      },
      { time: '2026-11-23 02:00:00', level: 'warn', event: 'cli_timeout', session_id: 'session-123' },
    ])
  } finally {
    await log.close()
    await rm(directory, { recursive: true, force: true })
  }
})
