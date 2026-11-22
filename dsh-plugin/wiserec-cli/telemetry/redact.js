const replacement = '[REDACTED]'
export const scanLimit = 128 * 1024
const rules = [
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)/gi, replacement],
  [/\b((?:set-cookie|cookie|authorization|proxy-authorization|x-ingest-token)["']?[ \t]*[:=][ \t]*)[^\r\n]*/gi, '$1' + replacement],
  [/\b(?:basic|bearer)[ \t]+[a-z0-9._~+/=-]+/gi, replacement],
  [/\b(?:pk-lf-|sk-lf-|sk-|gh[pousr]_|github_pat_|AKIA)[a-z0-9_-]+/gi, replacement],
  [/\b((?:x-csrftoken|csrftoken|csrf_token|password|passwd|secret|token|access[_-]?key|api[_-]?key)["']?[ \t]*[:=][ \t]*)(?:\[REDACTED\]|"(?:\\.|[^"\\])*(?:"|$)|'(?:\\.|[^'\\])*(?:'|$)|[^\s,;}&\]]+)/gi, '$1' + replacement],
  [/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, '$1' + replacement + '@'],
]

export function redactText(value, limit) {
  if (typeof value !== 'string' || !value) return undefined
  if (value.length > scanLimit) return `[OMITTED: ${value.length} chars]`
  let safe = value
  for (const [pattern, substitution] of rules) safe = safe.replace(pattern, substitution)
  if (safe.length <= limit) return safe
  return safe.slice(0, limit).replace(/[\uD800-\uDBFF]$/, '') + `…[TRUNCATED: ${safe.length} chars]`
}

export function textBlocks(content) {
  const selected = []
  let chars = 0
  if (Array.isArray(content)) {
    for (const part of content.slice(0, 64)) {
      if (part?.type !== 'text' || typeof part.text !== 'string') continue
      chars += part.text.length + 1
      if (chars > scanLimit) {
        const notice = '[OMITTED: oversized message]'
        return { content: [{ type: 'text', text: notice }], chars: notice.length }
      }
      selected.push({ type: 'text', text: part.text })
    }
  }
  return { content: selected, chars }
}

export function messageText(message, limit) {
  return redactText(textBlocks(message?.content).content.map(part => part.text).join('\n'), limit)
}

export function identifier(value) {
  if (typeof value !== 'string' || !/^[a-z0-9][a-z0-9._+@:/-]{0,127}$/i.test(value)) return undefined
  return redactText(value, 128)
}
