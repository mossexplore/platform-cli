import { open, readFile } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { createCollector } from './collector.js'
import { contextResolver } from './context.js'
import { createExporter } from './exporter.js'

export const name = 'wiserec-cli-telemetry'
export const inject = ['sessions']

const manifestPath = new URL('../package.json', import.meta.url)
const modes = new Set(['full', 'metadata_only'])
const integer = (value, fallback, min, max) => Number.isSafeInteger(value) && value >= min && value <= max
  ? value : fallback

async function userSettings() {
  const root = process.env.LOCALAPPDATA
  if (!root || !isAbsolute(root)) return {}
  try {
    const file = await open(join(root, 'WiseRec', 'dsh-plugins', 'wiserec-cli', 'config.json'), 'r')
    try {
      const { size } = await file.stat()
      if (size > 64 * 1024) return {}
      const data = Buffer.alloc(size + 1)
      const { bytesRead } = await file.read(data, 0, data.length, 0)
      if (bytesRead !== size) return {}
      const config = JSON.parse(data.toString('utf8', 0, bytesRead).replace(/^\uFEFF/, ''))
      const mode = config?.telemetry?.mode
      return {
        mode: mode === 'off' || mode === 'metadata_only' ? mode : undefined,
        mlPath: typeof config?.mlPath === 'string' && isAbsolute(config.mlPath) ? config.mlPath : undefined,
      }
    } finally {
      await file.close()
    }
  } catch {
    // The user settings file is optional. Bundle settings are used on a clean install.
    return {}
  }
}

function configuration(raw, localMode) {
  if (raw?.mode === 'off' || localMode === 'off') return { mode: 'off' }
  const endpoint = typeof raw?.endpoint === 'string' ? URL.parse(raw.endpoint) : null
  if (!endpoint || !['https:', 'http:'].includes(endpoint.protocol) ||
      !endpoint.hostname || endpoint.username || endpoint.password || endpoint.search || endpoint.hash ||
      endpoint.pathname !== '/v1/traces') throw new Error('invalid endpoint')
  const ingestToken = raw.ingestToken ?? ''
  if (typeof ingestToken !== 'string' || (ingestToken && !/^[!-~]{1,1024}$/.test(ingestToken))) {
    throw new Error('invalid ingest token')
  }
  const envs = endpoint.protocol === 'https:' && Array.isArray(raw.contentEnvironments)
    ? raw.contentEnvironments.slice(0, 64) : []
  return {
    endpoint: endpoint.href,
    ingestToken,
    mode: localMode === 'metadata_only' || !modes.has(raw.mode) ? 'metadata_only' : raw.mode,
    contentEnvironments: new Set(envs.length === 1 && envs[0] === '*' ? envs :
      envs.filter(value => typeof value === 'string' &&
        /^[a-z0-9][a-z0-9_.-]{0,63}$/i.test(value)).map(value => value.toLowerCase())),
    timeoutMs: integer(raw.timeoutMs, 4000, 100, 30_000),
    maxQueueSize: integer(raw.maxQueueSize, 50, 1, 100),
    maxPayloadChars: integer(raw.maxPayloadChars, 16_384, 128, 16_384),
  }
}

function reporter(ctx) {
  const recent = new Map()
  const counts = new Map()
  return (reason, count = 1) => {
    const total = (counts.get(reason) ?? 0) + count
    counts.set(reason, total)
    const now = Date.now()
    if (now - (recent.get(reason) ?? 0) >= 60_000) {
      recent.set(reason, now)
      ctx.logger?.warn?.(`WiseRec telemetry ${reason} (count=${total})`)
    }
  }
}

export function createBackend(contract, settings, pipeline) {
  const { SessionTelemetryBackend, SessionTelemetryCoordinator } = contract
  return class WiseRecSessionTelemetry extends SessionTelemetryBackend {
    static inject = ['sessions']
    #live = false

    constructor(ctx) {
      super(ctx)
      this.sharing = settings.mode === 'off' ? 'disabled' : 'full'
      if (settings.mode !== 'off') {
        new SessionTelemetryCoordinator(ctx, this, { capture: 'live', includeHistory: false })
        this.#live = true
      }
    }

    emit(record) {
      // The coordinator synchronously replays active sessions during initialization.
      if (this.#live) pipeline.emit(record)
    }

    async shutdown() {
      await pipeline?.shutdown()
    }
  }
}

export function startTelemetry(ctx, raw, {
  loadHost = () => import('@deepseek-ai/dsh-session-telemetry'),
  getUserSettings = userSettings,
  createPipeline = (settings, version, report, mlPath) => createCollector(settings, contextResolver(mlPath),
    createExporter(settings, version, report), report),
} = {}) {
  const report = reporter(ctx)
  let active = true
  ctx.effect(() => {
    void start().catch(() => { if (active) report('host_backend_failed') })
    return () => { active = false }
  }, 'wiserec-cli telemetry')

  async function start() {
    let local, settings
    try {
      local = await getUserSettings()
      settings = configuration(raw, local.mode)
    } catch {
      report('config_invalid')
      return
    }

    let contract, version
    try {
      contract = await loadHost()
      if (typeof contract.SessionTelemetryBackend !== 'function' ||
          typeof contract.SessionTelemetryCoordinator !== 'function') throw new Error('unsupported contract')
      version = JSON.parse(await readFile(manifestPath, 'utf8')).version
    } catch {
      if (active) report('host_library_unavailable')
      return
    }
    if (!active) return

    try {
      if (ctx.get('sessionTelemetry', false)) {
        report('host_backend_conflict')
        return
      }
      if (typeof ctx.sessions?.list !== 'function') {
        report('host_sessions_unavailable')
        return
      }
      // Keep the existing keepalive entry and its settings independent of telemetry.
      const pipeline = settings.mode === 'off' ? null : createPipeline(settings, version, report, local.mlPath)
      ctx.plugin(createBackend(contract, settings, pipeline))
    } catch {
      report('host_backend_failed')
    }
  }
}

export function apply(ctx, config) {
  startTelemetry(ctx, config)
}
