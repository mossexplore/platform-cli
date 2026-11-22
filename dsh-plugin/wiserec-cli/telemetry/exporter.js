import { envelope } from './mapper.js'

const maxBatch = 1024 * 1024
const maxQueueBytes = 4 * maxBatch
const maxResponse = 16 * 1024

function withoutContent(spans) {
  return spans.map(span => ({
    ...span,
    attributes: span.attributes.filter(({ key }) => key !== 'langfuse.observation.input' &&
      key !== 'langfuse.observation.output'),
  }))
}

async function responseBody(response) {
  if (!response.body) return {}
  const reader = response.body.getReader()
  const chunks = []
  let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > maxResponse) throw new Error('response limit')
      chunks.push(value)
    }
    const body = Buffer.concat(chunks).toString('utf8').trim()
    return body ? JSON.parse(body) : {}
  } finally {
    void reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

export function createExporter(settings, version, report, send = globalThis.fetch) {
  const queue = []
  const separator = ','
  // Only the spans list is filled during batching. Keep its resource envelope identical for every request.
  const empty = JSON.stringify(envelope([], version))
  const boundary = empty.lastIndexOf('[]')
  const head = empty.slice(0, boundary + 1)
  const tail = empty.slice(boundary + 1)
  const budget = maxBatch - Buffer.byteLength(head) - Buffer.byteLength(tail)
  let queuedBytes = 0
  let running
  let timer
  let closed = false
  let active
  let shuttingDown

  function shift() {
    const entry = queue.shift()
    queuedBytes -= entry.bytes + 1
    return entry
  }

  function schedule() {
    if (closed || running || timer) return
    timer = setTimeout(() => {
      timer = undefined
      flush()
    }, 35)
    timer.unref?.()
  }

  async function deliver(payload) {
    active = new AbortController()
    const signal = AbortSignal.any([active.signal, AbortSignal.timeout(settings.timeoutMs)])
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (settings.ingestToken) headers['X-Ingest-Token'] = settings.ingestToken
      const response = await send(settings.endpoint, { method: 'POST', body: payload, headers, redirect: 'error', signal })
      if (!response.ok) {
        void response.body?.cancel().catch(() => {})
        report('gateway_rejected')
        return
      }
      const result = await responseBody(response)
      const rejected = Number(result?.partialSuccess?.rejectedSpans ?? 0)
      if (Number.isSafeInteger(rejected) && rejected > 0) report('gateway_partial', rejected)
    } catch {
      report(signal.aborted ? 'delivery_timeout' : 'delivery_failed')
    } finally {
      active = undefined
    }
  }

  function flush() {
    if (running) return running
    clearTimeout(timer)
    timer = undefined
    running = Promise.resolve().then(async () => {
      while (queue.length) {
        const batch = [shift().body]
        let bytes = Buffer.byteLength(batch[0])
        while (queue.length && batch.length < 12 && bytes + 1 + queue[0].bytes <= budget) {
          bytes += queue[0].bytes + 1
          batch.push(shift().body)
        }
        await deliver(head + batch.join(separator) + tail)
      }
    }).finally(() => { running = undefined })
    return running
  }

  return {
    enqueue(spans) {
      if (closed || !spans.length) return
      const encode = values => values.map(value => JSON.stringify(value)).join(separator)
      let body = encode(spans)
      let bytes = Buffer.byteLength(body)
      if (bytes > budget) {
        report('oversized_content')
        body = encode(withoutContent(spans))
        bytes = Buffer.byteLength(body)
      }
      if (bytes > budget) {
        report('queue_dropped')
        return
      }
      let dropped = 0
      while (queue.length >= settings.maxQueueSize || queuedBytes + bytes + 1 > maxQueueBytes) {
        shift()
        dropped++
      }
      if (dropped) report('queue_dropped', dropped)
      queue.push({ body, bytes })
      queuedBytes += bytes + 1
      schedule()
    },
    flush,
    shutdown() {
      if (shuttingDown) return shuttingDown
      closed = true
      shuttingDown = (async () => {
        const deadline = setTimeout(() => {
          const dropped = queue.length
          queue.length = 0
          queuedBytes = 0
          if (dropped) report('queue_dropped', dropped)
          active?.abort()
        }, Math.min(1500, settings.timeoutMs))
        try {
          await flush()
        } finally {
          clearTimeout(deadline)
        }
      })()
      return shuttingDown
    },
  }
}
