import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setImmediate as tick } from 'node:timers/promises'
import test from 'node:test'
import { createCollector } from '../telemetry/collector.js'
import { contextResolver, readSession } from '../telemetry/context.js'
import { createExporter } from '../telemetry/exporter.js'
import { startTelemetry } from '../telemetry/index.js'
import { messageText, redactText } from '../telemetry/redact.js'

const settings = {
  mode: 'full', contentEnvironments: new Set(['sit', 'production-eu']),
  maxPayloadChars: 1024, maxQueueSize: 3, timeoutMs: 200,
  endpoint: 'https://telemetry.example.test/v1/traces', ingestToken: 'fixture-write-token',
}
const now = 1_790_000_000_000
const body = text => [{ type: 'text', text }]
const data = span => Object.fromEntries(span.attributes.map(({ key, value }) => [key, value.stringValue ?? value.intValue]))

function transcript(sink, id = 'session-001') {
  const endUser = { content: body('hello csrftoken=never-send-this'), source: { kind: 'user' } }
  const injected = { content: body('injected content'), source: { kind: 'context' } }
  const model = { source: { model: 'deepseek-demo', provider: 'deepseek' },
    content: [...body('model response sk-lf-donotforward'), { type: 'reasoning', text: 'model reasoning' }] }
  const events = [
    ['turn/start', { turn: 1 }],
    ['user/message', endUser], ['user/message', injected],
    ['step/start', { turn: 1, step: 1 }],
    ['request/header', { header: { config: { model: 'deepseek-demo', provider: 'deepseek' } } }],
    ['assistant/attempt', { turn: 1, step: 1, stream: ['not telemetry'] }],
    ['assistant/message', { turn: 1, step: 1, message: model,
      usage: { inputTokens: 10, outputTokens: 5, cacheReadTokens: 6 } }],
    ['tool/call', { turn: 1, step: 1, name: 'pwsh', callId: 'call-1',
      arguments: '{"command":"ml env list","token":"private token"}' }],
    ['tool/result', { turn: 1, step: 1, message: { toolCallId: 'call-1', content: body('tool response'), isError: true },
      meta: { kind: 'foreground', exitCode: -1, stdout: { spillPath: 'raw private path' } } }],
    ['turn/end', { turn: 1, reason: { kind: 'completed' } }],
  ]
  events.forEach(([type, body], seq) => sink.emit({
    channel: 'ledger', time: now + seq, attributes: { 'session.format_version': 4 },
    sourceEvent: { sessionId: id, envelope: { type, seq, surfaceOp: 'append' } }, body,
  }))
}

async function collect(context, configured = settings) {
  const delivered = []
  const sink = createCollector(configured, { start: () => undefined, finish: () => context }, {
    enqueue(spans) { delivered.push(spans) }, async shutdown() {},
  }, reason => assert.fail(reason))
  transcript(sink)
  await sink.shutdown()
  return delivered[0]
}

test('maps root, failed attempt, generation and tool with complete timing and metadata', async () => {
  const spans = await collect({ env: 'sit', businessId: 'biz-001', userId: 'employee', cliVersion: '1.1.1', bound: true })
  const [root, failed, model, tool] = spans
  assert.equal(root.traceId.length, 32)
  assert.equal(root.spanId.length, 16)
  assert.equal(root.endTimeUnixNano, String(BigInt(now + 9) * 1_000_000n))
  assert.equal(failed.parentSpanId, root.spanId)
  assert.equal(failed.status.code, 2)
  assert.equal(tool.parentSpanId, model.spanId)
  assert.equal(tool.status.code, 2)
  assert.equal(data(tool)['langfuse.observation.metadata.tool_exit_code'], '-1')
  assert.equal(data(model)['gen_ai.usage.input_tokens'], '16')
  assert.equal(data(model)['gen_ai.usage.output_tokens'], '5')
  assert.equal(data(root)['langfuse.observation.input'], 'hello csrftoken=[REDACTED]')
  assert.equal(data(root)['langfuse.observation.output'], 'model response [REDACTED]')
  for (const span of spans) {
    assert.equal(data(span)['langfuse.environment'], 'sit')
    assert.equal(data(span)['langfuse.user.id'], 'employee')
    assert.equal(data(span)['langfuse.trace.metadata.wiserec_business_id'], 'biz-001')
  }
  assert.doesNotMatch(JSON.stringify(spans), /never-send-this|donotforward|injected content|model reasoning|private token|raw private path/)
})

test('omits content for unknown, unbound, production and metadata-only modes', async () => {
  for (const [context, config] of [
    [{}, settings],
    [{ env: 'sit' }, settings],
    [{ env: 'production-eu', bound: true }, settings],
    [{ env: 'sit', bound: true }, { ...settings, mode: 'metadata_only' }],
    [{ env: 'sit', bound: true }, { ...settings, contentEnvironments: new Set() }],
    [{ env: 'sit' }, { ...settings, contentEnvironments: new Set(['*']) }],
  ]) {
    const spans = await collect(context, config)
    assert.equal(spans.length, 4)
    assert.doesNotMatch(JSON.stringify(spans), /langfuse\.observation\.(input|output)|injected|model response/)
  }
})

test('the wildcard includes bound production environments and still redacts content', async () => {
  const spans = await collect({ env: 'prod', bound: true }, { ...settings, contentEnvironments: new Set(['*']) })
  assert.equal(data(spans[0])['langfuse.environment'], 'prod')
  assert.equal(data(spans[0])['langfuse.observation.input'], 'hello csrftoken=[REDACTED]')
})

test('isolates concurrent sessions and does not upload a previously open or replayed turn', async () => {
  const result = []
  const sink = createCollector(settings, { start: () => null, finish: () => ({}) }, {
    enqueue: spans => result.push(spans), async shutdown() {},
  }, reason => assert.fail(reason))
  const emit = (id, type, seq, body) => sink.emit({
    channel: 'ledger', time: now + seq, sourceEvent: { sessionId: id, envelope: { type, seq } }, body,
  })
  emit('existing', 'turn/end', 22, { turn: 5, reason: { kind: 'completed' } })
  emit('closed', 'turn/start', 1, { turn: 2 })
  sink.emit({ channel: 'ops', attributes: { 'telemetry.op': 'shutdown', 'session.id': 'closed' } })
  emit('closed', 'turn/end', 2, { turn: 2, reason: { kind: 'completed' } })
  emit('a', 'turn/start', 1, { turn: 2 })
  emit('b', 'turn/start', 1, { turn: 3 })
  emit('a', 'turn/end', 2, { turn: 2, reason: { kind: 'aborted' } })
  emit('a', 'turn/end', 2, { turn: 2, reason: { kind: 'aborted' } })
  emit('b', 'turn/end', 2, { turn: 3, reason: { kind: 'completed' } })
  await sink.shutdown()
  assert.deepEqual(result.map(([root]) => data(root)['langfuse.session.id']), ['a', 'b'])
  assert.equal(result[0][0].status.code, 2)
  assert.notEqual(result[0][0].traceId, result[1][0].traceId)
})

test('validates the actual Go session file, auth attribution and changes during a turn', async t => {
  const root = await mkdtemp(join(tmpdir(), 'wiserec-telemetry-context-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const dir = join(root, 'ml-go-preview', 'sessions')
  await mkdir(dir, { recursive: true })
  const id = 'harness-session'
  const hash = createHash('sha256').update('dsh\0' + id).digest('hex').slice(0, 32)
  const file = join(dir, hash + '.json')
  const original = { version: 1, source: 'dsh', session_id: id, current: 'sit', updated_at: '2026-11-22T11:01:00Z',
    selections: { sit: { businessId: 'biz', username: 'employee' }, prod: { businessId: 'private-business' } } }
  await writeFile(file, JSON.stringify(original))
  let cli = { '会话 ID': id, '当前环境': 'sit', '当前业务': 'biz', 'CLI 版本': '1.1.1', Cookie: 'ignore' }
  const resolver = contextResolver('', { readState: value => readSession(value, root), readCLI: () => cli })
  const start = await resolver.start(id)
  assert.deepEqual(await resolver.finish(id, start), { env: 'sit', businessId: 'biz', userId: 'employee', cliVersion: '1.1.1', bound: true })
  cli = { ...cli, '当前业务': '未绑定' }
  assert.deepEqual(await resolver.finish(id, start), { env: 'sit', cliVersion: '1.1.1' })
  await writeFile(file, JSON.stringify({ ...original, updated_at: '2026-11-22T11:02:00Z' }))
  assert.deepEqual(await resolver.finish(id, start), { cliVersion: '1.1.1' })
  await writeFile(file, JSON.stringify({ ...original, session_id: 'other-session' }))
  assert.equal(await resolver.start(id), undefined)
})

test('redacts credentials before truncation and excludes other content blocks', () => {
  for (const input of [
    'Cookie: session=fixture',
    'x-csrftoken=fixture',
    '{"password":"a \\" fixture"}',
    'Bearer fixture',
    'Authorization: Basic fixture',
    'sk-lf-fixture ghp_fixture',
    '-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----',
  ]) assert.doesNotMatch(redactText(input, 128), /fixture/)
  assert.match(redactText('a'.repeat(150) + ' token=fixture', 50), /TRUNCATED/)
  assert.match(redactText('a'.repeat(300000), 1024), /OMITTED/)
  assert.equal(messageText({ content: [{ type: 'file', file: 'fixture' }, ...body('text')] }, 100), 'text')
  assert.equal(redactText('sample csrftoken=[REDACTED]', 128), 'sample csrftoken=[REDACTED]')
})

test('bounds queue, serializes OTLP batches and reports rejected requests and partial success', async () => {
  const reports = [], requests = []
  const exporter = createExporter(settings, '0.1.2', (...values) => reports.push(values), async (url, options) => {
    requests.push(JSON.parse(options.body))
    assert.equal(url, settings.endpoint)
    assert.equal(options.headers['X-Ingest-Token'], settings.ingestToken)
    assert.equal(options.redirect, 'error')
    if (requests.length === 1) return new Response('{"partialSuccess":{"rejectedSpans":"1"}}')
    return new Response('error', { status: 502 })
  })
  for (let i = 0; i < 5; i++) exporter.enqueue([{ name: `turn-${i}`, attributes: [] }])
  await exporter.flush()
  exporter.enqueue([{ name: 'still-works', attributes: [] }])
  await exporter.shutdown()
  assert.deepEqual(requests[0].resourceSpans[0].scopeSpans[0].spans.map(x => x.name), ['turn-2', 'turn-3', 'turn-4'])
  assert.deepEqual(reports, [['queue_dropped', 1], ['queue_dropped', 1], ['gateway_partial', 1], ['gateway_rejected']])
})

test('uses a short cancellable request and keeps later deliveries functional', async () => {
  const reports = []
  let calls = 0
  const exporter = createExporter({ ...settings, timeoutMs: 100 }, '0.1.2', value => reports.push(value), async (_, { signal }) => {
    calls++
    if (calls > 1) return new Response('{}')
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }))
  })
  exporter.enqueue([{ name: 'first', attributes: [] }])
  const keepAlive = setTimeout(() => {}, 300)
  try {
    await exporter.flush()
    exporter.enqueue([{ name: 'second', attributes: [] }])
    await exporter.shutdown()
  } finally {
    clearTimeout(keepAlive)
  }
  assert.equal(calls, 2)
  assert.deepEqual(reports, ['delivery_timeout'])
})

test('isolates missing host library, occupied backend, and the runtime off switch', { timeout: 5000 }, async () => {
  for (const state of ['missing', 'occupied', 'off', 'active']) {
    const calls = []
    const messages = []
    let settle
    const settled = new Promise(resolve => { settle = resolve })
    const ctx = {
      sessions: { list: () => [] },
      get: () => state === 'occupied' ? {} : undefined,
      effect(fn) { fn() },
      plugin(Type) {
        calls.push(new Type(ctx))
        settle()
      },
      logger: { warn(value) {
        messages.push(value)
        settle()
      } },
    }
    class Backend {}
    class Coordinator {
      constructor(_, backend, capture) { calls.push([backend.sharing, capture]) }
    }
    let configuredEnvironments
    startTelemetry(ctx, { endpoint: settings.endpoint, mode: 'full', contentEnvironments: ['*'] }, {
      async getUserSettings() { return state === 'off' ? { mode: 'off' } : {} },
      async loadHost() {
        if (state === 'missing') throw new Error('private path')
        return { SessionTelemetryBackend: Backend, SessionTelemetryCoordinator: Coordinator }
      },
      createPipeline(configuration) {
        configuredEnvironments = [...configuration.contentEnvironments]
        return {}
      },
    })
    await settled
    if (state === 'missing' || state === 'occupied') {
      assert.equal(calls.length, 0)
      assert.match(messages[0], state === 'missing' ? /host_library_unavailable/ : /host_backend_conflict/)
    } else {
      assert.equal(messages.length, 0)
      assert.equal(calls.at(-1)?.sharing, state === 'off' ? 'disabled' : 'full')
      if (state === 'active') {
        assert.deepEqual(calls[0], ['full', { capture: 'live', includeHistory: false }])
        assert.deepEqual(configuredEnvironments, ['*'])
      } else {
        assert.equal(calls.length, 1)
      }
    }
  }
})
