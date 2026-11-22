import { execFile } from 'node:child_process'
import { access } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

export const protocol = 'dsh-keepalive-v1'
const sessionVariables = new Set(['DSH_SHELL', 'DSH_SESSION_ID', 'ML_SESSION_ID'])
const requestIdPattern = /^[a-z0-9-]{1,64}$/i

export function hostEnvironment(environment) {
  return Object.fromEntries(Object.entries(environment).filter(([key]) => !sessionVariables.has(key.toUpperCase())))
}

function execute(binary, args, { timeout, signal, input, acceptErrorResponse = false }) {
  return new Promise((resolve, reject) => {
    const child = execFile(binary, args, {
      timeout, signal, windowsHide: true, encoding: 'utf8', maxBuffer: 16 * 1024,
      env: hostEnvironment(process.env),
    }, (error, stdout) => {
      if (error && !(acceptErrorResponse && Number.isInteger(error.code) && stdout && !signal?.aborted)) {
        const reason = signal?.aborted ? 'cancelled' : error.killed ? 'timeout' : 'invocation_failed'
        reject(new Error(reason))
      } else {
        resolve(stdout)
      }
    })
    child.stdin?.on('error', () => {})
    child.stdin?.end(input)
  })
}

export async function findCLI(configured, environment = process.env, platform = process.platform) {
  if (configured) {
    return checkExecutable(configured)
  }
  if (platform !== 'win32') throw new Error('missing_cli')
  const systemRoot = environment.SystemRoot
  if (systemRoot && isAbsolute(systemRoot)) {
    try {
      const output = await execute(join(systemRoot, 'System32', 'reg.exe'), [
        'query', 'HKCU\\Software\\WiseRec\\CLIGo', '/v', 'Path',
      ], { timeout: 4000 })
      const folder = /^\s*Path[ \t]+REG_SZ[ \t]+([^\r\n]+)/im.exec(output)?.[1]?.trim()
      if (folder && isAbsolute(folder)) {
        const candidate = join(folder, 'ml.exe')
        await access(candidate)
        return candidate
      }
    } catch {
      // A portable installation can still use an explicit path.
    }
  }
  const local = environment.LOCALAPPDATA
  if (local && isAbsolute(local)) {
    return checkExecutable(join(local, 'Programs', 'WiseRecCLIGo', 'ml.exe'))
  }
  throw new Error('missing_cli')
}

async function checkExecutable(path) {
  try {
    await access(path)
    return path
  } catch (error) {
    throw new Error(error.code === 'ENOENT' || error.code === 'ENOTDIR' ? 'missing_cli' : 'cli_access_failed')
  }
}

function parseResponse(stdout) {
  try {
    const result = JSON.parse(stdout)
    if (result && typeof result === 'object' && !Array.isArray(result)) return result
  } catch {
    // The child may return malformed output or no compatible protocol.
  }
  throw new Error('invalid_response')
}

export function createRunner(config) {
  let connection
  return async (action, hostID, sessionID, signal) => {
    if (!connection) {
      const binary = await findCLI(config.mlPath)
      const stdout = await execute(binary, ['auth', 'ping', 'tick', '--capabilities'], { timeout: 6000, signal })
      const capability = parseResponse(stdout)
      if (capability.protocol !== protocol || !Number.isSafeInteger(capability.budget_ms) ||
          capability.budget_ms < 1000 || capability.budget_ms > 240_000) {
        throw new Error('incompatible_cli')
      }
      const timeout = capability.budget_ms + 5000
      if (config.timeoutSeconds && config.timeoutSeconds * 1000 < timeout) {
        throw new Error('invalid_timeout')
      }
      connection = { binary, timeout: config.timeoutSeconds ? config.timeoutSeconds * 1000 : timeout }
    }
    try {
      const stdout = await execute(connection.binary, ['auth', 'ping', 'tick', '--json'], {
        timeout: connection.timeout, signal, acceptErrorResponse: true,
        input: JSON.stringify({ protocol, action, host_id: hostID, session_id: sessionID }),
      })
      const result = parseResponse(stdout)
      if (result.protocol !== protocol || typeof result.state !== 'string') throw new Error('invalid_response')
      return {
        state: result.state,
        env: result.env,
        lastConfirmed: result.last_confirmed_at,
        retryPending: result.retry_pending === true,
        contextChanged: result.context_changed === true,
        requestID: typeof result.request_id === 'string' && requestIdPattern.test(result.request_id) ? result.request_id : '',
      }
    } catch (error) {
      if (!signal?.aborted) connection = undefined
      throw error
    }
  }
}
