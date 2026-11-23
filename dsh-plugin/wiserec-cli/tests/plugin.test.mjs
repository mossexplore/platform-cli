import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdir, mkdtemp, readdir, readFile, rm, utimes, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setImmediate, setTimeout as delay } from 'node:timers/promises'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import { loadPluginConfiguration } from '../config.js'
import { apply, startScheduler } from '../index.js'
import { cleanupKeepaliveLogs, createKeepaliveLog } from '../logging.js'
import { hostEnvironment } from '../runner.js'
import { createSessionStatus } from '../session-status.js'
import { startSessionTitles } from '../session-title.js'

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

async function waitForTitle(check) {
  const deadline = Date.now() + 3000
  while (!check() && Date.now() < deadline) await delay(10)
  assert.ok(check(), 'expected session title update')
}

test('names isolated sessions by tenant and preserves a manual rename across restart', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-titles-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host([a, b])
  const snapshots = new Map()
  const reads = new Map()
  const contexts = new Map([
    ['session-a', { '当前环境': 'sit', '当前租户': '', '登录状态': '有效' }],
    ['session-b', { '当前环境': 'uat', '当前租户': '搜索平台', '登录状态': '有效' }],
  ])
  let seq = 0
  ctx.sessionTitle = {
    get: session => snapshots.get(session),
    rename(session, title) {
      const snapshot = { source: { kind: 'user' }, title, eventSeq: ++seq, updatedAt: seq }
      snapshots.set(session, snapshot)
      return snapshot
    },
  }
  const start = () => startSessionTitles(ctx, config, directory, async id => {
    reads.set(id, (reads.get(id) ?? 0) + 1)
    return { '会话 ID': id, '当前业务': 'team-business-id', ...contexts.get(id) }
  })
  let stop = start()
  try {
    await waitForTitle(() => seq === 2)
    assert.equal(snapshots.get(a.session).title, 'sit环境')
    assert.equal(snapshots.get(b.session).title, 'uat环境 · 搜索平台')
    contexts.get('session-a')['当前租户'] = '推荐平台'
    emit('agent/status', a, 'idle')
    await waitForTitle(() => seq === 3)
    assert.equal(snapshots.get(a.session).title, 'sit环境 · 推荐平台')
    await stop()

    // The same title text can be saved by hand, with a different event sequence.
    const manual = ctx.sessionTitle.rename(a.session, snapshots.get(a.session).title)
    contexts.get('session-a')['当前租户'] = '其他租户'
    contexts.get('session-b')['当前环境'] = 'sit'
    stop = start()
    await waitForTitle(() => snapshots.get(b.session).title === 'sit环境 · 搜索平台')
    assert.equal(snapshots.get(a.session), manual)

    const count = reads.get('session-a')
    contexts.get('session-b')['登录状态'] = '已过期'
    contexts.get('session-b')['当前租户'] = '其他租户'
    emit('agent/status', b, 'idle')
    emit('agent/status', a, 'idle')
    await waitForTitle(() => reads.get('session-a') > count)
    assert.equal(snapshots.get(b.session).title, 'sit环境 · 搜索平台')
    assert.equal(seq, 5)
  } finally {
    await stop()
  }
})

test('ignores old CLI output and a context read that completed after session disposal', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-titles-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host([a, b])
  const renamed = []
  ctx.sessionTitle = { get: () => undefined, rename: (...args) => { renamed.push(args) } }
  let reading
  const started = new Promise(resolve => { reading = resolve })
  let finish
  const reply = new Promise(resolve => { finish = resolve })
  const stop = startSessionTitles(ctx, config, directory, async id => {
    if (id === 'session-a') return { '会话 ID': id, '当前环境': 'sit' }
    reading()
    return reply
  })
  await started
  emit('agent/disposed', b)
  finish({ '会话 ID': 'session-b', '当前环境': 'uat', '登录状态': '有效', '当前租户': '' })
  await stop()
  assert.deepEqual(renamed, [])
})

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

test('projects per-session badge status and discards stale, paused and replaced results correctly', async () => {
  const a = agent('session-a')
  const b = agent('session-b')
  const { ctx, emit } = host([a, b])
  let now = 1000
  const tickInterval = 60_000
  const statuses = createSessionStatus(tickInterval, () => now)
  const route = statuses.register({ connection: { fetch: { register: definition => definition } } })
  const snapshot = () => route.fetch().json()
  const stop = startScheduler(ctx, { ...config, idleWindowMinutes: 10 }, async (action, _hostId, id) => {
    if (action === 'release') return { state: 'released' }
    if (id === 'session-a') return {
      state: 'not_due', env: 'dev', lastConfirmed: '2026-11-22 12:00:00', requestID: 'private-request',
    }
    return { state: 'login_expired', env: 'uat' }
  }, () => now, undefined, statuses.update)
  try {
    await setImmediate()
    assert.deepEqual(await snapshot(), {
      'session-a': { state: 'healthy', env: 'dev', checkedAt: 1000, lastConfirmed: '2026-11-22 12:00:00' },
      'session-b': { state: 'expired', env: 'uat', checkedAt: 1000 },
    })
    statuses.update('session-a', { state: 'not_due', env: 'dev', retryPending: true })
    assert.equal((await snapshot())['session-a'].state, 'uncertain')
    statuses.update('session-a', { state: 'confirmed', env: 'dev', contextChanged: true })
    assert.deepEqual((await snapshot())['session-a'], { state: 'unchecked', checkedAt: 1000 })
    now += 4 * tickInterval
    assert.equal((await snapshot())['session-b'].state, 'unchecked')
    emit('agent/disposed', b)
    await setImmediate()
    assert.equal((await snapshot())['session-b'], undefined)
    statuses.update('session-a', { state: 'paused' })
    assert.equal((await snapshot())['session-a'].state, 'paused')
  } finally {
    await stop()
  }
  assert.deepEqual(await snapshot(), {})
})

test('renders session badge colors and Beijing times through the DSH client module', async () => {
  const checkedAt = Date.parse('2026-11-22T06:30:00Z')
  const state = {
    'session-a': { state: 'healthy', env: 'dev', checkedAt, lastConfirmed: '2026-11-22 14:29:00' },
    'session-b': { state: 'expired', env: 'uat' },
    'session-c': { state: 'uncertain' },
    'session-d': { state: 'paused' },
  }
  let loaded
  let dictionary
  const slots = new Map()
  const disposers = []
  const source = await readFile(new URL('../client.js', import.meta.url), 'utf8')
  runInNewContext(source, {
    window: { __ModuleLoader__: { load(definition) { loaded = definition } } },
    AbortController, AbortSignal, setTimeout: () => undefined, clearTimeout: () => {},
    async fetch(path) {
      assert.equal(path, '/api/wiserec-cli/keepalive-status')
      return Response.json(state)
    },
  })
  assert.equal(loaded.id, 'dsh-wiserec-cli')
  const client = loaded.factory(name => {
    assert.equal(name, 'react')
    return {
      createElement: (tag, props, ...children) => ({ tag, props, children }),
      useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(),
    }
  })
  client.apply({
    locale: { register(_namespace, dictionaries) { dictionary = dictionaries.zh } },
    effect(activate) { disposers.push(activate()) },
    slots: {
      inject(_name, activate) { activate() },
      register({ name }, component) { slots.set(name, component) },
    },
  })
  const t = (key, options) => dictionary[key].replace('{value}', options?.value)
  try {
    await setImmediate()
    const Mark = slots.get('sidebar.session.row.trailing')
    const Detail = slots.get('sidebar.session.row.hover')
    for (const [sessionId, color, label] of [
      ['session-a', '#459a62', 'WiseRec 保活正常'],
      ['session-b', '#ce5058', 'WiseRec 登录已过期'],
      ['session-c', '#b88016', 'WiseRec 保活待确认'],
      ['session-d', '#858a96', 'WiseRec 保活已暂停'],
    ]) {
      const badge = Mark({ sessionId, t })
      assert.equal(badge.props.style.color, color)
      assert.equal(badge.props['aria-label'], label)
    }
    assert.equal(Mark({ sessionId: 'unknown', t }), null)
    assert.deepEqual(Detail({ sessionId: 'session-a', t }).children.map(item => item.children[0]), [
      'WiseRec 保活正常', '环境 dev', '最近检查 2026-11-22 14:30:00', '环境上次续期成功 2026-11-22 14:29:00',
    ])
  } finally {
    for (const dispose of disposers.reverse()) dispose?.()
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

test('creates user config and layers it over Profile options without overwriting edits', async () => {
  const root = await mkdtemp(join(tmpdir(), 'wiserec-user-config-'))
  const directory = join(root, 'WiseRec')
  const path = join(directory, 'config.json')
  const profile = { mlPath: join(root, 'ml.exe'), pollSeconds: 180, timeoutSeconds: 45 }
  try {
    const initial = loadPluginConfiguration(profile, { directory })
    assert.deepEqual(initial.issues, [])
    assert.deepEqual(initial.config, {
      enabled: true, ...profile, idleWindowMinutes: 120,
    })
    const created = JSON.parse(await readFile(path, 'utf8'))
    assert.deepEqual(Object.keys(created), ['logging'])
    assert.deepEqual(initial.logOptions, {
      directory: join(directory, 'logs'), cleanupEnabled: true, limit: 256 * 1024,
      maxBytes: 10240 * 1024, maxAgeMs: 7 * 86400_000, cleanupIntervalMs: 86400_000,
    })

    const user = '\ufeff' + JSON.stringify({
      pollSeconds: 60, logging: { directoryName: 'logs-test', maxFileKB: 8, retentionMinutes: 2 },
    })
    await writeFile(path, user)
    const resolved = loadPluginConfiguration(profile, { directory })
    assert.deepEqual(resolved.issues, [])
    assert.deepEqual(resolved.config, { ...initial.config, pollSeconds: 60 })
    assert.deepEqual(resolved.logOptions, {
      ...initial.logOptions, directory: join(directory, 'logs-test'), limit: 8 * 1024, maxAgeMs: 120_000,
    })
    assert.equal(await readFile(path, 'utf8'), user)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('Windows plugin startup creates config and logs under LOCALAPPDATA', { skip: process.platform !== 'win32' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'wiserec-localappdata-'))
  const previous = process.env.LOCALAPPDATA
  process.env.LOCALAPPDATA = root
  const { ctx } = host()
  const { logger } = loggingContext(Date.parse('2026-11-22T12:00:00Z'))
  let close
  try {
    apply({ ...ctx, logger, inject() {}, effect(activate) { close = activate() } })
    await close()
    const directory = join(root, 'WiseRec', 'dsh-plugins', 'wiserec-cli')
    const config = JSON.parse(await readFile(join(directory, 'config.json'), 'utf8'))
    assert.equal(config.logging.retentionMinutes, 10080)
    const records = (await readFile(join(directory, 'logs', `keepalive-${process.pid}.jsonl`), 'utf8'))
      .trim().split('\n').map(JSON.parse)
    assert.deepEqual(records.map(record => record.event), ['scheduler_started', 'log_cleanup_completed'])
  } finally {
    try {
      await close?.()
    } finally {
      if (previous === undefined) delete process.env.LOCALAPPDATA
      else process.env.LOCALAPPDATA = previous
      await rm(root, { recursive: true, force: true })
    }
  }
})

test('logs invalid config but skips automatic cleanup and keeps valid runtime settings', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-invalid-config-'))
  const path = join(directory, 'config.json')
  const ctx = loggingContext(Date.parse('2026-11-22T12:00:00Z'))
  try {
    await writeFile(path, '{invalid')
    const invalidFile = loadPluginConfiguration({ pollSeconds: 90 }, { directory })
    assert.deepEqual(invalidFile.issues, [{ reason: 'invalid_json' }])
    assert.equal(invalidFile.logOptions.cleanupEnabled, false)
    assert.equal(invalidFile.config.pollSeconds, 90)

    await writeFile(path, JSON.stringify({ pollSeconds: 60, logging: {
      directoryName: '../other-logs', cleanupIntervalMinutes: 36_000,
    } }))
    const { config: resolved, logOptions, issues } = loadPluginConfiguration({}, { directory })
    assert.equal(resolved.pollSeconds, 60)
    assert.equal(logOptions.cleanupEnabled, false)
    assert.equal(logOptions.directory, join(directory, 'logs'))
    const log = createKeepaliveLog(ctx, logOptions)
    for (const issue of issues) log.record('config_invalid', issue)
    log.record('scheduler_started')
    await log.close()
    const records = (await readFile(join(logOptions.directory, `keepalive-${process.pid}.jsonl`), 'utf8'))
      .trim().split('\n').map(JSON.parse)
    assert.deepEqual(records, [
      { time: '2026-11-22 20:00:00', level: 'warn', event: 'config_invalid',
        reason: 'invalid_field', field: 'logging.directoryName' },
      { time: '2026-11-22 20:00:00', level: 'warn', event: 'config_invalid',
        reason: 'invalid_field', field: 'logging.cleanupIntervalMinutes' },
      { time: '2026-11-22 20:00:00', level: 'info', event: 'scheduler_started' },
    ])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

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
      {
        time: '2026-11-23 02:00:00', level: 'info', event: 'log_cleanup_completed',
        trigger: 'startup', expired_deleted: 0, capacity_deleted: 0, deleted_kb: 0,
      },
    ])
  } finally {
    await log.close()
    await rm(directory, { recursive: true, force: true })
  }
})

const day = 24 * 60 * 60 * 1000
const retentionTime = Date.parse('2026-11-22T12:00:00Z')

async function writeLog(directory, name, age, bytes = 3) {
  const path = join(directory, name)
  await writeFile(path, Buffer.alloc(bytes))
  const mtime = new Date(retentionTime - age * day)
  await utimes(path, mtime, mtime)
}

test('removes expired segments only for exited hosts, including during concurrent cleanup', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-log-expiry-'))
  const exitedPID = process.pid + 1
  const subdirectory = `keepalive-${exitedPID + 2}.jsonl`
  const recentLog = `keepalive-${exitedPID}.jsonl`
  const kept = [
    `keepalive-${process.pid}.previous.jsonl`, `keepalive-${exitedPID + 1}.jsonl`,
    'other.jsonl', `keepalive-${exitedPID}.jsonl.bak`,
  ]
  try {
    await mkdir(join(directory, subdirectory))
    await Promise.all([
      ...kept.map(name => writeLog(directory, name, 8)),
      writeLog(directory, `keepalive-${exitedPID}.previous.jsonl`, 8),
      writeLog(directory, recentLog, 2),
    ])
    const options = { now: retentionTime, isHostExited: pid => pid === exitedPID || pid === process.pid }
    const results = await Promise.all([
      cleanupKeepaliveLogs(directory, options), cleanupKeepaliveLogs(directory, options),
    ])
    assert.equal(results.reduce((sum, result) => sum + result.expiredDeleted, 0), 1)
    assert.equal(results.reduce((sum, result) => sum + result.deletedBytes, 0), 3)
    for (const result of results) {
      assert.equal(result.capacityDeleted, 0)
      assert.equal(result.reason, undefined)
    }
    assert.deepEqual((await readdir(directory)).sort(), [...kept, recentLog, subdirectory].sort())
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('enforces a soft directory limit by pruning the oldest exited host logs first', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-log-limit-'))
  const newestPID = process.pid + 3
  const activeLog = `keepalive-${process.pid}.jsonl`
  const newestLog = `keepalive-${newestPID}.jsonl`
  try {
    await Promise.all([
      writeLog(directory, activeLog, 6),
      writeLog(directory, `keepalive-${newestPID - 2}.previous.jsonl`, 5),
      writeLog(directory, `keepalive-${newestPID - 1}.jsonl`, 3),
      writeLog(directory, newestLog, 1),
    ])
    const options = { now: retentionTime, maxBytes: 8, isHostExited: () => true }
    assert.deepEqual(await cleanupKeepaliveLogs(directory, options), {
      expiredDeleted: 0, capacityDeleted: 2, deletedBytes: 6,
    })
    assert.deepEqual((await readdir(directory)).sort(), [activeLog, newestLog].sort())
    assert.deepEqual(await cleanupKeepaliveLogs(directory, { ...options, maxBytes: 1 }), {
      expiredDeleted: 0, capacityDeleted: 1, deletedBytes: 3,
    })
    assert.deepEqual(await readdir(directory), [activeLog])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('retains partial deletion counts and recovers abandoned cleanup claims', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'wiserec-log-partial-'))
  const removedPID = process.pid + 1
  const blockedPID = process.pid + 2
  const priorOwner = process.pid + 3
  const pending = `keepalive-${removedPID}.previous.jsonl.cleanup-${priorOwner}-aa329a7f-1632-4e40-b325-5b2e25f5506b`
  const blocked = `keepalive-${blockedPID}.jsonl`
  try {
    await writeLog(directory, pending, 9, 1285)
    await writeLog(directory, blocked, 8)
    const options = {
      now: retentionTime,
      isHostExited(pid) {
        if (pid === blockedPID) throw new Error('unavailable file deletion check')
        return true
      },
    }
    assert.deepEqual(await cleanupKeepaliveLogs(directory, options), {
      expiredDeleted: 1, capacityDeleted: 0, deletedBytes: 1285, reason: 'delete_failed',
    })
    assert.deepEqual(await readdir(directory), [blocked])
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('uses configured retention, capacity and cleanup interval in a test log directory', { timeout: 3000 }, async t => {
  const root = await mkdtemp(join(tmpdir(), 'wiserec-log-summary-'))
  await writeFile(join(root, 'config.json'), JSON.stringify({ logging: {
    directoryName: 'logs-test', maxFileKB: 4, maxTotalKB: 8, retentionMinutes: 2, cleanupIntervalMinutes: 1,
  } }))
  const { logOptions, issues } = loadPluginConfiguration({}, { directory: root })
  assert.deepEqual(issues, [])
  const directory = logOptions.directory
  const normalDirectory = join(root, 'logs')
  await Promise.all([mkdir(directory), mkdir(normalDirectory)])
  const removedPID = process.pid + 1
  const oldName = `keepalive-${removedPID}.jsonl`
  const testLog = join(directory, oldName)
  const oldTime = new Date(retentionTime - 3 * 60_000)
  await writeFile(testLog, Buffer.alloc(1285))
  await utimes(testLog, oldTime, oldTime)
  await writeLog(normalDirectory, oldName, 9)
  await writeLog(directory, `keepalive-${removedPID}.previous.jsonl`, 0, 16 * 1024)
  t.mock.method(Date, 'now', () => retentionTime)
  t.mock.timers.enable({ apis: ['setInterval'] })
  t.mock.method(process, 'kill', (pid, signal) => {
    assert.equal(signal, 0)
    assert.equal(pid, removedPID)
    throw Object.assign(new Error('process already exited'), { code: 'ESRCH' })
  })

  const ctx = loggingContext(retentionTime)
  const startup = new Promise(resolve => {
    ctx.logger.exporter({ export(message) { if (message.args[1]?.trigger === 'startup') resolve() } })
  })
  const log = createKeepaliveLog(ctx, logOptions)
  try {
    await startup
    await setImmediate()
    t.mock.timers.tick(60_000)
    await log.close()
    const records = (await readFile(join(directory, `keepalive-${process.pid}.jsonl`), 'utf8'))
      .trim().split('\n').map(JSON.parse)
    assert.deepEqual(records, [
      {
        time: '2026-11-22 20:00:00', level: 'info', event: 'log_cleanup_completed',
        trigger: 'startup', expired_deleted: 1, capacity_deleted: 1, deleted_kb: 17.25,
      },
      {
        time: '2026-11-22 20:00:00', level: 'info', event: 'log_cleanup_completed',
        trigger: 'periodic', expired_deleted: 0, capacity_deleted: 0, deleted_kb: 0,
      },
    ])
    assert.deepEqual(await readdir(normalDirectory), [oldName])
  } finally {
    await log.close()
    await rm(root, { recursive: true, force: true })
  }
})
