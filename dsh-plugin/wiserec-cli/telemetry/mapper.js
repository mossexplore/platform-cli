import { createHash } from 'node:crypto'
import { identifier, redactText } from './redact.js'

const errorReasons = new Set(['error', 'aborted', 'blocked', 'interrupted', 'max-tokens', 'forked'])
const acceptedReasons = new Set(['completed', ...errorReasons])

function id(value, length) {
  return createHash('sha256').update(value).digest('hex').slice(0, length)
}

function nano(ms) {
  return String(BigInt(Math.max(1, Math.trunc(ms))) * 1_000_000n)
}

function attrs(fields) {
  return Object.entries(fields).flatMap(([key, v]) => {
    if (typeof v === 'string' && v) return [{ key, value: { stringValue: v } }]
    if (Number.isSafeInteger(v)) return [{ key, value: { intValue: String(v) } }]
    return []
  })
}

function content(input, output, allowed) {
  if (!allowed) return {}
  return {
    'langfuse.observation.input': input,
    'langfuse.observation.output': output,
  }
}

function usageFields(usage) {
  const valid = v => Number.isSafeInteger(v) && v >= 0
  const input = valid(usage?.inputTokens) && usage.inputTokens +
    (valid(usage.cacheReadTokens) ? usage.cacheReadTokens : 0) +
    (valid(usage.cacheWriteTokens) ? usage.cacheWriteTokens : 0)
  return {
    'gen_ai.usage.input_tokens': input,
    'gen_ai.usage.output_tokens': valid(usage?.outputTokens) ? usage.outputTokens : undefined,
    'gen_ai.usage.cache_read.input_tokens': valid(usage?.cacheReadTokens) ? usage.cacheReadTokens : undefined,
    'gen_ai.usage.cache_creation.input_tokens': valid(usage?.cacheWriteTokens) ? usage.cacheWriteTokens : undefined,
  }
}

export function turnSpans(turn, end, context, settings) {
  const { time, reason } = end
  const seed = JSON.stringify(['dsh-wiserec-cli', turn.id, turn.format, turn.seq])
  const traceId = id(seed, 32)
  const rootId = id(seed + ':turn', 16)
  const env = context.env?.toLowerCase()
  const allowed = settings.mode === 'full' && context.bound && env && (
    settings.contentEnvironments.has('*') ||
    (!/(?:^|[-_.])prod(?:uction)?(?:$|[-_.])/.test(env) && settings.contentEnvironments.has(env))
  )
  const common = {
    'langfuse.session.id': redactText(turn.id, 128),
    'langfuse.user.id': redactText(context.userId, 128),
    'langfuse.environment': context.env,
    'langfuse.trace.metadata.wiserec_business_id': context.businessId,
    'langfuse.trace.metadata.wiserec_cli_version': context.cliVersion,
  }
  const span = (name, spanId, parentSpanId, started, ended, fields, error) => ({
    traceId, spanId, ...(parentSpanId ? { parentSpanId } : {}),
    name, kind: 1, startTimeUnixNano: nano(started), endTimeUnixNano: nano(Math.max(started, ended)),
    ...(error ? { status: { code: 2 } } : {}),
    attributes: attrs({ ...common, ...fields }),
  })
  const result = [span('dsh.turn', rootId, undefined, turn.start, time, {
    'langfuse.observation.type': 'span',
    'langfuse.observation.metadata.turn_reason': acceptedReasons.has(reason) ? reason : 'other',
    ...content(turn.input, turn.output, allowed),
  }, errorReasons.has(reason))]

  const parents = new Map()
  for (const attempt of turn.generations) {
    const spanId = id(seed + ':generation:' + attempt.seq, 16)
    parents.set(attempt.step, spanId)
    const model = identifier(attempt.model)
    result.push(span(model ? `chat ${model}` : 'chat', spanId, rootId, attempt.start, attempt.end, {
      'langfuse.observation.type': 'generation',
      'gen_ai.operation.name': 'chat',
      'gen_ai.request.model': model,
      'gen_ai.provider.name': identifier(attempt.provider),
      ...usageFields(attempt.usage),
      ...content(undefined, attempt.output, allowed),
    }, attempt.error))
  }
  for (const tool of turn.tools.values()) {
    const name = identifier(tool.name) ?? 'unknown'
    const status = tool.status ?? 'interrupted'
    const ended = tool.end ?? time
    result.push(span(`tool ${name}`, id(seed + ':tool:' + tool.seq, 16), parents.get(tool.step) ?? rootId,
      tool.start, ended, {
        'langfuse.observation.type': 'tool',
        'langfuse.observation.metadata.tool_name': name,
        'langfuse.observation.metadata.tool_status': status,
        'langfuse.observation.metadata.tool_exit_code': tool.exitCode,
        'langfuse.observation.metadata.tool_duration_ms': Math.max(0, ended - tool.start),
        ...content(tool.input, tool.output, allowed),
      }, status !== 'ok'))
  }
  return result
}

export function envelope(spans, pluginVersion) {
  return {
    resourceSpans: [{
      resource: { attributes: attrs({
        'service.name': 'dsh-wiserec-cli',
        'service.version': pluginVersion,
        'os.type': process.platform === 'win32' ? 'windows' : process.platform,
      }) },
      scopeSpans: [{ scope: { name: 'dsh-wiserec-cli', version: pluginVersion }, spans }],
    }],
  }
}
