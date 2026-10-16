'use strict';
document.querySelectorAll('[data-ranking-top]').forEach(select => {
  const panel = select.closest('.analytics-ranking');
  const tbody = panel.querySelector('tbody');
  const error = document.createElement('p');
  error.className = 'hint';
  error.setAttribute('role', 'alert');
  error.hidden = true;
  panel.append(error);
  let previous = select.value;
  let active;
  let sequence = 0;
  select.addEventListener('change', async () => {
    active?.abort();
    const controller = new AbortController();
    active = controller;
    const ticket = ++sequence;
    const value = select.value;
    const url = new URL(panel.dataset.rankingUrl, location.href);
    document.querySelectorAll('[data-ranking-top]').forEach(input => url.searchParams.set(input.name, input.value));
    const kind = select.name === 'commands_top' ? 'commands' : 'actors';
    error.hidden = true;
    panel.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {headers: {'X-Fragment': `ranking-${kind}`}, signal: controller.signal});
      if (ticket !== sequence) return;
      if (response.redirected) { location.assign(response.url); return; }
      if (!response.ok) throw new Error('榜单加载失败，请重试');
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (ticket !== sequence) return;
      const rows = html.querySelector('[data-ranking-rows]');
      if (!rows) throw new Error('榜单响应异常，请重试');
      tbody.replaceChildren(...rows.childNodes);
      previous = value;
      const current = new URL(location.href);
      current.searchParams.set(select.name, value);
      // Keep the original query window pinned even when the page used the default range.
      current.searchParams.set('begin', url.searchParams.get('begin'));
      current.searchParams.set('end', url.searchParams.get('end'));
      history.replaceState(null, '', current);
    } catch (problem) {
      if (ticket !== sequence || problem.name === 'AbortError') return;
      select.value = previous;
      error.textContent = problem.message === 'Failed to fetch' ? '连接中断，原榜单已保留，请重试' : problem.message;
      error.hidden = false;
    } finally {
      if (ticket === sequence) panel.removeAttribute('aria-busy');
    }
  });
});
