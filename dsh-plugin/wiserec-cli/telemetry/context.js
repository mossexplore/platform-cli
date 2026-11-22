import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { open } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { promisify } from 'node:util'
import { findCLI, hostEnvironment } from '../runner.js'
import { identifier } from './redact.js'

const execute = promisify(execFile)
const maxStateBytes = 256 * 1024

export async function readSession(id, root = process.env.APPDATA) {
  if (!root || !isAbsolute(root)) return undefined
  const fileName = createHash('sha256').update('dsh\0').update(id).digest('hex').slice(0, 32) + '.json'
  try {
    const file = await open(join(root, 'ml-go-preview', 'sessions', fileName), 'r')
    try {
      const details = await file.stat()
      if (!details.isFile() || details.size > maxStateBytes) return undefined
      const buffer = Buffer.alloc(details.size + 1)
      const { bytesRead } = await file.read(buffer, 0, buffer.length, 0)
      if (bytesRead !== details.size) return undefined
      const state = JSON.parse(buffer.toString('utf8', 0, bytesRead))
      const env = identifier(state?.current)
      if (state?.version !== 1 || state.source !== 'dsh' || state.session_id !== id ||
          !env || typeof state.updated_at !== 'string' || !Number.isFinite(Date.parse(state.updated_at))) return undefined
      const selection = Object.hasOwn(state.selections ?? {}, env) ? state.selections[env] : undefined
      const username = selection?.username
      return {
        env,
        businessId: identifier(selection?.businessId),
        username: typeof username === 'string' && username.length <= 128 ? username : undefined,
        updated: state.updated_at,
      }
    } finally {
      await file.close()
    }
  } catch {
    return undefined
  }
}

async function readCLIContext(id, mlPath, signal) {
  const binary = await findCLI(mlPath)
  const { stdout } = await execute(binary, ['context', '--json'], {
    timeout: 2000, signal, windowsHide: true, maxBuffer: 16 * 1024,
    env: { ...hostEnvironment(process.env), DSH_SHELL: '1', DSH_SESSION_ID: id },
  })
  return JSON.parse(stdout)
}

export function contextResolver(mlPath, { readState = readSession, readCLI = readCLIContext } = {}) {
  return {
    start: readState,
    async finish(id, before, signal) {
      let cli
      try {
        cli = await readCLI(id, mlPath, signal)
      } catch {
        // An absent CLI or an uninitialized profile is common in a new DSH session.
      }
      const cliVersion = identifier(cli?.['CLI 版本'])
      const after = await readState(id)
      if (!before || !after || before.env !== after.env || before.updated !== after.updated ||
          before.username !== after.username || before.businessId !== after.businessId ||
          (cli && (cli['会话 ID'] !== id || cli['当前环境'] !== after.env))) {
        return { cliVersion }
      }
      if (!after.businessId || cli?.['当前业务'] !== after.businessId) {
        return { env: after.env, cliVersion }
      }
      return { env: after.env, businessId: after.businessId, userId: after.username, cliVersion, bound: true }
    },
  }
}
