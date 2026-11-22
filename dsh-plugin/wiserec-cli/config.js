import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { isAbsolute, join } from 'node:path'

const defaults = JSON.parse(readFileSync(new URL('./config.json', import.meta.url), 'utf8'))
const bytesPerKB = 1024
const msPerMinute = 60_000
const maxMinutes = Math.floor(Number.MAX_SAFE_INTEGER / msPerMinute)
const maxKB = Math.floor(Number.MAX_SAFE_INTEGER / bytesPerKB)

function integer(value, min, max) {
  return Number.isSafeInteger(value) && value >= min && value <= max
}

const pluginValidators = {
  enabled: value => typeof value === 'boolean',
  mlPath: value => typeof value === 'string' && (value === '' || isAbsolute(value)),
  pollSeconds: value => integer(value, 60, 180),
  idleWindowMinutes: value => integer(value, 1, maxMinutes),
  timeoutSeconds: value => integer(value, 0, 300),
}

const logValidators = {
  directoryName: value => typeof value === 'string' && /^[a-z0-9_-]{1,64}$/i.test(value) &&
    !/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(value),
  maxFileKB: value => integer(value, 1, maxKB),
  maxTotalKB: value => integer(value, 1, maxKB),
  retentionMinutes: value => integer(value, 1, maxMinutes),
  cleanupIntervalMinutes: value => integer(value, 1, Math.floor(0x7fffffff / msPerMinute)),
}

export const configurationFields = new Set([
  ...Object.keys(pluginValidators), 'logging', ...Object.keys(logValidators).map(key => `logging.${key}`),
])

function logLimits(logging) {
  return {
    limit: logging.maxFileKB * bytesPerKB,
    maxBytes: logging.maxTotalKB * bytesPerKB,
    maxAgeMs: logging.retentionMinutes * msPerMinute,
    cleanupIntervalMs: logging.cleanupIntervalMinutes * msPerMinute,
  }
}

export const defaultLogLimits = logLimits(defaults.logging)

function windowsDirectory() {
  const root = process.env.LOCALAPPDATA
  if (process.platform === 'win32' && root && isAbsolute(root)) {
    return join(root, 'WiseRec', 'dsh-plugins', 'wiserec-cli')
  }
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function readUserConfiguration(directory, issues) {
  if (!directory) return {}
  const path = join(directory, 'config.json')
  let text
  try {
    text = readFileSync(path, 'utf8')
  } catch (error) {
    if (error.code !== 'ENOENT') {
      issues.push({ reason: 'read_failed' })
      return {}
    }
    try {
      mkdirSync(directory, { recursive: true, mode: 0o700 })
      // Seed only the new log options so existing Profile settings retain their scope.
      writeFileSync(path, `${JSON.stringify({ logging: defaults.logging }, null, 2)}\n`, { flag: 'wx', mode: 0o600 })
      return { logging: defaults.logging }
    } catch (createError) {
      if (createError.code !== 'EEXIST') {
        issues.push({ reason: 'create_failed' })
        return {}
      }
      try {
        text = readFileSync(path, 'utf8')
      } catch {
        issues.push({ reason: 'read_failed' })
        return {}
      }
    }
  }
  try {
    const file = JSON.parse(text.replace(/^\uFEFF/, ''))
    if (isObject(file)) return file
  } catch {
    // Fall back to known settings with automatic deletion paused.
  }
  issues.push({ reason: 'invalid_json' })
  return {}
}

function resolveFields(validators, base, profile, user, issues, prefix = '') {
  const resolved = {}
  for (const [key, validate] of Object.entries(validators)) {
    resolved[key] = base[key]
    for (const layer of [user, profile]) {
      if (!Object.hasOwn(layer, key)) continue
      if (validate(layer[key])) {
        resolved[key] = layer[key]
        break
      }
      const field = prefix + key
      if (!issues.some(issue => issue.field === field)) issues.push({ reason: 'invalid_field', field })
    }
  }
  return resolved
}

export function loadPluginConfiguration(profile = {}, { directory = windowsDirectory() } = {}) {
  const issues = []
  const user = readUserConfiguration(directory, issues)
  const legacy = isObject(profile) ? profile : {}
  const config = resolveFields(pluginValidators, defaults, legacy, user, issues)
  const profileLog = isObject(legacy.logging) ? legacy.logging : {}
  const userLog = isObject(user.logging) ? user.logging : {}
  // An explicitly supplied user section can replace malformed legacy settings.
  const logSource = Object.hasOwn(user, 'logging') ? user : legacy
  if (Object.hasOwn(logSource, 'logging') && !isObject(logSource.logging)) {
    issues.push({ reason: 'invalid_field', field: 'logging' })
  }
  const logging = resolveFields(logValidators, defaults.logging, profileLog, userLog, issues, 'logging.')
  return {
    config,
    issues,
    logOptions: {
      directory: directory && join(directory, logging.directoryName),
      cleanupEnabled: !issues.some(issue => !issue.field || issue.field.startsWith('logging')),
      ...logLimits(logging),
    },
  }
}
