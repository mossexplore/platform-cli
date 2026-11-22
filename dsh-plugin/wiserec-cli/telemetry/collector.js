import { identifier, messageText, redactText, scanLimit, textBlocks } from './redact.js'
import { turnSpans } from './mapper.js'

const events = new Set([
  'turn/start', 'turn/end', 'step/start', 'request/header', 'request/context',
  'user/message', 'assistant/message', 'assistant/attempt', 'tool/call', 'tool/result',
])
const maxTurns = 32
const maxRecords = 256
const maxTurnChars = 128 * 1024
const maxPendingChars = 4 * 1024 * 1024

function sourceOf(record) {
  const source = record?.sourceEvent
  const event = source?.envelope
  if (record?.channel !== 'ledger' || !identifier(source?.sessionId) || !events.has(event?.type) ||
      !Number.isSafeInteger(event.seq) || event.seq < 0 || !Number.isSafeInteger(record.time) || record.time <= 0) return
  return { session: source.sessionId, event }
}

const integer = value => Number.isSafeInteger(value) ? value : undefined

function project(record, session, event, capture) {
  const data = record.body
  if (!data || typeof data !== 'object') return
  const user = event.type === 'user/message'
  const message = user ? data : data.message
  const source = message?.source
  const projected = {
    turn: integer(data.turn), step: integer(data.step),
    reason: { kind: identifier(data.reason?.kind) },
    interrupted: data.interrupted === true,
    callId: typeof data.callId === 'string' && data.callId.length <= 256 ? data.callId : undefined,
    name: identifier(data.name),
  }
  let chars = 0
  if (message) {
    const text = capture && (!user || (source?.kind === 'user' && event.surfaceOp === 'append'))
      ? textBlocks(message.content) : { content: [], chars: 0 }
    chars = text.chars
    const selected = {
      content: text.content,
      source: { kind: identifier(source?.kind), model: identifier(source?.model), provider: identifier(source?.provider) },
      toolCallId: typeof message.toolCallId === 'string' && message.toolCallId.length <= 256 ? message.toolCallId : undefined,
      isError: message.isError === true,
    }
    if (user) Object.assign(projected, selected)
    else projected.message = selected
  }
  if (event.type === 'tool/call' && capture && typeof data.arguments === 'string') {
    projected.arguments = data.arguments.length > scanLimit ? '[OMITTED: oversized arguments]' : data.arguments
    chars += projected.arguments.length
  }
  if (event.type === 'tool/result' && data.meta?.kind === 'foreground') {
    projected.meta = { kind: 'foreground', exitCode: integer(data.meta.exitCode) }
  }
  if (data.usage) {
    const usage = data.usage
    projected.usage = { inputTokens: integer(usage.inputTokens), outputTokens: integer(usage.outputTokens),
      cacheReadTokens: integer(usage.cacheReadTokens), cacheWriteTokens: integer(usage.cacheWriteTokens) }
  }
  const config = event.type === 'request/header' ? data.header?.config : data
  return {
    session, type: event.type, seq: event.seq, appended: event.surfaceOp === 'append',
    time: record.time, format: integer(record.attributes?.['session.format_version']),
    data: projected, model: identifier(config?.model), provider: identifier(config?.provider), chars,
  }
}

function appendText(previous, next, limit) {
  if (!previous || !next) return previous ?? next
  return redactText(previous + '\n' + next, limit)
}

function route(turn, config) {
  if (!config || typeof config !== 'object') return
  turn.model = identifier(config.model) ?? turn.model
  turn.provider = identifier(config.provider) ?? turn.provider
}

function eligibleContent(turn, producer) {
  if (turn.contentChars >= maxTurnChars) return undefined
  const content = producer()
  if (content) turn.contentChars += content.length
  return content
}

function generation(turn, time, event, data, limit, capture) {
  if (!Number.isSafeInteger(data.step) || turn.generations.length >= 32) return
  const message = data.message
  const output = capture ? eligibleContent(turn, () => messageText(message, limit)) : undefined
  if (output) turn.output = output
  const start = turn.attemptStarted.get(data.step) ?? turn.steps.get(data.step) ?? turn.start
  turn.attemptStarted.set(data.step, time)
  turn.generations.push({
    seq: event.seq, step: data.step, start, end: time,
    model: message?.source?.model ?? turn.model, provider: message?.source?.provider ?? turn.provider,
    output, usage: data.usage, error: !message || data.interrupted === true,
  })
}

function toolResult(turn, time, data, limit, capture) {
  const tool = turn.tools.get(data.message?.toolCallId)
  if (!tool || tool.status) return
  const shellResult = (tool.name === 'pwsh' || tool.name === 'bash') && data.meta?.kind === 'foreground'
  const exit = shellResult ? data.meta.exitCode : undefined
  tool.exitCode = Number.isSafeInteger(exit) ? exit : undefined
  tool.end = time
  tool.status = data.message.isError === true || (tool.exitCode !== undefined && tool.exitCode !== 0) ? 'error' : 'ok'
  if (capture) tool.output = eligibleContent(turn, () => messageText(data.message, limit))
}

export function createCollector(settings, context, exporter, report) {
  const turns = new Map()
  const pending = []
  const finishing = new Set()
  const stop = new AbortController()
  const limit = settings.maxPayloadChars
  const capture = settings.mode === 'full' && settings.contentEnvironments.size > 0
  let immediate
  let pendingChars = 0
  let closed = false
  let shutdown

  function finish(turn, data, time) {
    if (finishing.size >= 8) {
      report('context_dropped')
      return
    }
    const task = Promise.resolve(turn.before)
      .then(before => context.finish(turn.id, before, stop.signal))
      .then(fields => {
        if (!stop.signal.aborted) exporter.enqueue(turnSpans(turn, { time, reason: data.reason?.kind }, fields, settings))
      })
      .catch(() => report('context_failed'))
      .finally(() => finishing.delete(task))
    finishing.add(task)
  }

  function accept(event) {
    const { data, session, time } = event
    if (event.type === 'turn/start') {
      if (!Number.isSafeInteger(data.turn)) return
      if (!turns.has(session) && turns.size >= maxTurns) {
        turns.delete(turns.keys().next().value)
        report('capture_dropped')
      }
      turns.set(session, {
        id: session, format: event.format,
        seq: event.seq, lastSeq: event.seq, number: data.turn, start: time, contentChars: 0,
        before: Promise.resolve().then(() => context.start(session)).catch(() => undefined),
        steps: new Map(), attemptStarted: new Map(), generations: [], tools: new Map(),
      })
      return
    }
    const turn = turns.get(session)
    if (!turn || event.seq <= turn.lastSeq || (data.turn !== undefined && data.turn !== turn.number)) return
    turn.lastSeq = event.seq
    switch (event.type) {
      case 'turn/end':
        turns.delete(session)
        finish(turn, data, time)
        break
      case 'step/start':
        if (turn.steps.size < 32 && Number.isSafeInteger(data.step)) turn.steps.set(data.step, time)
        break
      case 'request/header':
      case 'request/context':
        route(turn, event)
        break
      case 'user/message':
        if (capture && data.source?.kind === 'user' && event.appended) {
          turn.input = appendText(turn.input, eligibleContent(turn, () => messageText(data, limit)), limit)
        }
        break
      case 'assistant/message':
      case 'assistant/attempt':
        generation(turn, time, event, data, limit, capture)
        break
      case 'tool/call':
        if (turn.tools.size < 64 && typeof data.callId === 'string' && data.callId.length <= 256 &&
            !turn.tools.has(data.callId)) {
          turn.tools.set(data.callId, {
            seq: event.seq, step: data.step, name: identifier(data.name), start: time,
            input: capture ? eligibleContent(turn, () => redactText(data.arguments, limit)) : undefined,
          })
        }
        break
      case 'tool/result':
        toolResult(turn, time, data, limit, capture)
        break
    }
  }

  function drain() {
    clearImmediate(immediate)
    immediate = undefined
    pendingChars = 0
    for (const event of pending.splice(0)) {
      if (!event.type) {
        turns.delete(event.session)
        continue
      }
      try {
        accept(event)
      } catch {
        turns.delete(event.session)
        report('capture_failed')
      }
    }
  }

  return {
    emit(record) {
      if (closed) return
      if (record?.channel === 'ops' && record.attributes?.['telemetry.op'] === 'shutdown') {
        // Disposal markers follow pending ledger events; drain them in the same order.
        const session = record.attributes?.['session.id']
        if (identifier(session) && pending.length < maxRecords) pending.push({ session })
      } else {
        const source = sourceOf(record)
        if (!source) return
        const event = project(record, source.session, source.event, capture)
        if (!event) return
        if (pending.length >= maxRecords || pendingChars + event.chars > maxPendingChars) {
          pending.length = 0
          pendingChars = 0
          turns.clear()
          report('capture_dropped')
        }
        pending.push(event)
        pendingChars += event.chars
      }
      if (!immediate) immediate = setImmediate(drain)
    },
    shutdown() {
      if (shutdown) return shutdown
      closed = true
      shutdown = (async () => {
        drain()
        turns.clear()
        let timer
        const deadline = new Promise(resolve => {
          timer = setTimeout(() => { stop.abort(); resolve() }, 500)
        })
        try {
          await Promise.race([Promise.allSettled(finishing), deadline])
        } finally {
          clearTimeout(timer)
          await exporter.shutdown()
        }
      })()
      return shutdown
    },
  }
}
