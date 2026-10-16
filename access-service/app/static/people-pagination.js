'use strict';
(() => {
  const panel = document.querySelector('[data-people-list]');
  if (!panel) return;
  const table = panel.querySelector('.people-table');
  const scroll = table.closest('.table-scroll');
  const error = panel.querySelector('[data-people-load-error]');
  let active;
  let sequence = 0;
  async function load(url, push = true) {
    active?.abort();
    const controller = new AbortController();
    active = controller;
    const ticket = ++sequence;
    scroll.style.minHeight = `${Math.max(scroll.clientHeight, parseFloat(scroll.style.minHeight) || 0)}px`;
    panel.setAttribute('aria-busy', 'true');
    error.hidden = true;
    try {
      const response = await fetch(url, {headers: {'X-Fragment': 'people'}, signal: controller.signal});
      if (ticket !== sequence) return;
      if (response.redirected) { location.assign(response.url); return; }
      if (!response.ok) throw new Error('人员列表加载失败，请重试');
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (ticket !== sequence) return;
      const rows = html.querySelector('[data-people-rows]');
      const pager = html.querySelector('.pagination');
      const dialogs = html.querySelector('[data-people-dialogs]');
      if (!rows || !pager || !dialogs) throw new Error('人员列表响应异常，请重试');
      table.tBodies[0].replaceChildren(...rows.childNodes);
      panel.querySelector('.pagination').replaceWith(pager);
      document.querySelector('[data-people-dialogs]').replaceChildren(...dialogs.childNodes);
      if (push) history.pushState(null, '', url);
      document.dispatchEvent(new Event('people-page-updated'));
    } catch (problem) {
      if (ticket !== sequence || problem.name === 'AbortError') return;
      error.textContent = problem.message === 'Failed to fetch' ? '连接中断，原列表已保留，请重试' : problem.message;
      error.hidden = false;
    } finally {
      if (ticket === sequence) panel.removeAttribute('aria-busy');
    }
  }
  panel.addEventListener('click', event => {
    const link = event.target.closest('.pagination a');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    load(link.href);
  });
  panel.addEventListener('submit', event => {
    const form = event.target.closest('.page-jump');
    if (!form) return;
    event.preventDefault();
    const url = new URL(form.action, location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    load(url.href);
  });
  window.addEventListener('popstate', () => load(location.href, false));
})();
