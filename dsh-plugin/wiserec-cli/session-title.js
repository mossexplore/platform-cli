import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { readCLIContext } from './runner.js'

function desiredTitle(context, id) {
  if (context?.['会话 ID'] !== id || context['登录状态'] !== '有效' ||
      typeof context['当前环境'] !== 'string' || typeof context['当前租户'] !== 'string') return
  const singleLine = value => value.replace(/[\p{Cc}\p{Zl}\p{Zp}]+/gu, ' ').trim()
  const env = singleLine(context['当前环境'])
  if (!env || env === '未绑定') return
  const tenant = singleLine(context['当前租户'])
  return tenant ? `${env}环境 · ${tenant}` : `${env}环境`
}

async function readOwnership(path) {
  try {
    return JSON.parse(await readFile(path, 'utf8'))
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
}

async function saveOwnership(path, accepted, desired) {
  const temp = `${path}.${randomUUID()}.tmp`
  const { title, eventSeq, updatedAt } = accepted
  try {
    await writeFile(temp, JSON.stringify({ title, eventSeq, updatedAt, desired }), { flag: 'wx', mode: 0o600 })
    await rename(temp, path)
  } finally {
    await rm(temp, { force: true })
  }
}

export function startSessionTitles(ctx, config, directory, readContext = readCLIContext) {
  const titles = ctx.sessionTitle
  if (typeof titles?.get !== 'function' || typeof titles.rename !== 'function') return
  const pending = new Set()
  let active
  let closed = false

  async function update(agent, session, id, signal) {
    const key = createHash('sha256').update(id).digest('hex')
    const path = join(directory, `${key}.json`)
    const owned = await readOwnership(path)
    if (signal.aborted) return
    const context = await readContext(id, config.mlPath, signal)
    const desired = desiredTitle(context, id)
    if (!desired) return
    await mkdir(directory, { recursive: true, mode: 0o700 })
    if (signal.aborted || agent.status === 'running' || agent.session !== session || session.header?.id !== id) return

    // The host records both plugin and manual renames as user titles. Only
    // replace a pinned title when its exact event belongs to this plugin.
    const current = titles.get(session)
    if (owned) {
      if (current?.source?.kind !== 'user' || current.eventSeq !== owned.eventSeq ||
          current.updatedAt !== owned.updatedAt || current.title !== owned.title) return
      if (owned.desired === desired) return
    } else if (current?.source?.kind === 'user') {
      return
    }
    const accepted = titles.rename(session, desired)
    await saveOwnership(path, accepted, desired)
  }

  function drain() {
    if (closed || active || pending.size === 0) return
    const agent = pending.values().next().value
    pending.delete(agent)
    const session = agent.session
    const id = session?.header?.id
    if (typeof id !== 'string' || !id || agent.status === 'running') {
      queueMicrotask(drain)
      return
    }
    const controller = new AbortController()
    const done = update(agent, session, id, controller.signal)
      // Old CLIs and temporarily unavailable sessions are retried on refresh.
      .catch(() => {})
      .finally(() => {
        active = undefined
        drain()
      })
    active = { agent, session, controller, done }
  }

  function cancel(agent) {
    pending.delete(agent)
    if (active?.agent === agent) active.controller.abort()
  }

  function refresh(agent, status = agent.status) {
    if (status === 'running') {
      cancel(agent)
      return
    }
    if (active?.agent === agent && active.session !== agent.session) cancel(agent)
    pending.add(agent)
    drain()
  }

  function refreshLiveAgents() {
    for (const agent of ctx.agents.list()) refresh(agent)
  }

  const listeners = [
    ctx.on('agent/created', ({ agent }) => refresh(agent)),
    ctx.on('agent/session-start', ({ agent }) => refresh(agent)),
    ctx.on('agent/status', ({ agent, status }) => refresh(agent, status)),
    ctx.on('agent/disposed', ({ agent }) => cancel(agent)),
  ]
  refreshLiveAgents()
  const timer = setInterval(refreshLiveAgents, config.pollSeconds * 1000)
  timer.unref()
  return async () => {
    closed = true
    clearInterval(timer)
    for (const dispose of listeners) dispose()
    pending.clear()
    active?.controller.abort()
    await active?.done
  }
}
