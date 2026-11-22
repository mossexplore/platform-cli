const statusPath = '/api/wiserec-cli/keepalive-status'
const uncertain = new Set([
  'retrying', 'in_flight', 'legacy_worker', 'local_error', 'invalid_request', 'cli_timeout', 'cli_failed',
])

function sessionState(result) {
  if (result.contextChanged) return 'unchecked'
  if (result.state === 'expired' || result.state === 'login_expired') return 'expired'
  if (uncertain.has(result.state) || result.retryPending) return 'uncertain'
  if (result.state === 'confirmed' || result.state === 'not_due') return 'healthy'
  if (['paused', 'disabled', 'stopped'].includes(result.state)) return 'paused'
  if (result.state === 'login_unavailable') return 'login-required'
  if (result.state === 'waiting_business') return 'business-required'
  return 'unchecked'
}

export function createSessionStatus(pollMs, clock = Date.now) {
  const entries = new Map()
  return {
    update(sessionId, result) {
      if (!result) {
        entries.delete(sessionId)
        return
      }
      if (result.state === 'paused') {
        entries.set(sessionId, { ...entries.get(sessionId), state: 'paused' })
        return
      }
      const checkedAt = result.state === 'unchecked' ? undefined : clock()
      const state = sessionState(result)
      const env = !result.contextChanged && typeof result.env === 'string' &&
        result.env.length <= 256 && !/\p{Cc}/u.test(result.env) ? result.env : undefined
      const lastConfirmed = !result.contextChanged && typeof result.lastConfirmed === 'string' &&
        /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(result.lastConfirmed) ? result.lastConfirmed : undefined
      entries.set(sessionId, { state, env, checkedAt, lastConfirmed })
    },
    register(ctx) {
      return ctx.connection.fetch.register({
        path: statusPath,
        methods: ['GET'],
        requestBody: 'buffered',
        fetch() {
          const staleBefore = clock() - 3 * pollMs
          const snapshot = Object.fromEntries(Array.from(entries, ([id, value]) => [
            id, value.state !== 'paused' && value.checkedAt < staleBefore ? { ...value, state: 'unchecked' } : value,
          ]))
          return Response.json(snapshot, { headers: { 'Cache-Control': 'no-store' } })
        },
      })
    },
  }
}
