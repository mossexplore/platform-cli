import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { startScheduler } from '../index.js'
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
