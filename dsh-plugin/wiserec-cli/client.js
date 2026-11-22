window.__ModuleLoader__.load({
  id: 'dsh-wiserec-cli',
  factory(require) {
    const { createElement, useSyncExternalStore } = require('react')
    const namespace = 'wiserec.keepalive'
    const colors = new Map([
      ['healthy', '#459a62'], ['expired', '#ce5058'], ['uncertain', '#b88016'],
      ['paused', '#858a96'], ['unchecked', '#858a96'],
      ['login-required', '#858a96'], ['business-required', '#858a96'],
    ])
    const dictionaries = {
      zh: {
        healthy: 'WiseRec 保活正常', expired: 'WiseRec 登录已过期', uncertain: 'WiseRec 保活待确认',
        paused: 'WiseRec 保活已暂停', unchecked: 'WiseRec 保活未检查',
        'login-required': 'WiseRec 等待登录', 'business-required': 'WiseRec 等待选择业务',
        environment: '环境 {value}', checked: '最近检查 {value}', confirmed: '环境上次续期成功 {value}',
      },
      en: {
        healthy: 'WiseRec keepalive active', expired: 'WiseRec login expired', uncertain: 'WiseRec keepalive unconfirmed',
        paused: 'WiseRec keepalive paused', unchecked: 'WiseRec keepalive unchecked',
        'login-required': 'WiseRec login required', 'business-required': 'WiseRec business selection required',
        environment: 'Environment {value}', checked: 'Last checked {value}', confirmed: 'Environment last renewed {value}',
      },
    }

    function apply(ctx) {
      let entries = new Map()
      const listeners = new Set()
      const subscribe = listener => {
        listeners.add(listener)
        return () => listeners.delete(listener)
      }
      function useStatus(sessionId) {
        return useSyncExternalStore(subscribe, () => entries.get(sessionId))
      }

      ctx.effect(() => {
        const controller = new AbortController()
        let timer
        async function refresh() {
          let snapshot = new Map()
          try {
            const response = await fetch('/api/wiserec-cli/keepalive-status', {
              cache: 'no-store', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
            })
            if (response.ok) snapshot = new Map(Object.entries(await response.json()))
          } catch {
            // An unavailable host must not leave old results visible.
          }
          if (controller.signal.aborted) return
          entries = snapshot
          timer = setTimeout(refresh, 10_000)
          for (const listener of listeners) listener()
        }
        void refresh()
        return () => {
          controller.abort()
          clearTimeout(timer)
        }
      }, 'WiseRec keepalive status polling')

      ctx.effect(() => ctx.locale.register(namespace, dictionaries), 'WiseRec keepalive status locale')
      function Mark({ sessionId, t }) {
        const status = useStatus(sessionId)
        if (!colors.has(status?.state)) return null
        const label = t(status.state)
        return createElement('span', {
          role: 'img', 'aria-label': label, title: label,
          style: { color: colors.get(status.state), fontSize: '12px', lineHeight: 1 },
        }, '●')
      }
      function Detail({ sessionId, t }) {
        const status = useStatus(sessionId)
        if (!colors.has(status?.state)) return null
        const checkedAt = Number.isFinite(status.checkedAt)
          ? new Date(status.checkedAt + 8 * 60 * 60 * 1000).toISOString().slice(0, 19).replace('T', ' ')
          : undefined
        return createElement('div', null,
          createElement('strong', null, t(status.state)),
          status.env && createElement('div', null, t('environment', { value: status.env })),
          checkedAt && createElement('div', null, t('checked', { value: checkedAt })),
          status.lastConfirmed && createElement('div', null, t('confirmed', { value: status.lastConfirmed })),
        )
      }
      for (const [name, Component] of [
        ['sidebar.session.row.trailing', Mark], ['sidebar.session.row.hover', Detail],
      ]) {
        ctx.slots.inject(name, () => ctx.slots.register({ name, id: namespace, order: 20, locale: namespace }, Component))
      }
    }

    return { apply, inject: ['slots', 'locale'] }
  },
})
