'use strict';
// Keep one-time credentials in this document only; no browser storage or URL tokens.
function clearNotificationToken() {
  const result = document.querySelector('[data-token-result]');
  const field = result?.querySelector('textarea');
  if (field) { field.value = ''; field.defaultValue = ''; field.textContent = ''; }
  if (result) result.hidden = true;
}
function notificationMessage(form, message) {
  const error = form.querySelector('[data-token-error]');
  error.textContent = message;
  error.hidden = false;
  error.focus();
}
document.addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-token-form]');
  if (!form) return;
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  if (submit.disabled) return;
  const data = new FormData(form);
  submit.disabled = true;
  const label = submit.textContent;
  submit.textContent = '正在生成…';
  form.querySelector('[data-token-error]').hidden = true;
  try {
    const response = await fetch(form.action, {method: 'POST', headers: {'Accept': 'application/json'}, body: data});
    if (!response.headers.get('content-type')?.includes('application/json')) {
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      throw new Error(html.querySelector('[role="alert"]')?.textContent || '登录或表单已失效，请刷新页面后重试。');
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '生成未完成，请刷新后核对凭据状态。');
    const html = new DOMParser().parseFromString(result.html, 'text/html');
    const main = html.querySelector('#main');
    if (!main) throw new Error('显示凭据失败，请刷新页面核对后重新生成。');
    form.closest('dialog')?.close();
    clearNotificationToken();
    document.querySelector('#main').replaceWith(main);
    window.history.replaceState(null, '', result.url);
    const field = main.querySelector('[data-token-result] textarea');
    field.focus();
    field.scrollIntoView({block: 'center'});
  } catch (error) {
    notificationMessage(form, error.message || '连接中断，请刷新核对凭据状态，避免重复生成。');
  } finally {
    submit.disabled = false;
    submit.textContent = label;
  }
});
document.addEventListener('click', async (event) => {
  if (event.target.closest('[data-token-copy]')) {
    const field = document.querySelector('[data-token-result] textarea');
    const status = document.querySelector('[data-token-copy-status]');
    try {
      if (!navigator.clipboard) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(field.value);
      status.textContent = 'Token 已复制，请在30分钟内绑定。';
    } catch (_) {
      field.focus();
      field.select();
      status.textContent = '自动复制不可用，已选中 Token，请按 Ctrl+C（Mac：⌘C）复制。';
    }
  }
  if (event.target.closest('[data-token-close]')) {
    clearNotificationToken();
    document.querySelector('[data-token-trigger]')?.focus();
  }
});
// A closed confirmation never retains its previous confirmation text or error.
document.addEventListener('close', (event) => {
  const form = event.target.querySelector?.('[data-token-form]');
  if (form) {
    form.querySelector('[name="confirmation"]').value = '';
    form.querySelector('[data-token-error]').hidden = true;
  }
}, true);
window.addEventListener('pagehide', clearNotificationToken);
// HTML fallback responses also replace the POST address with a safe GET location.
if (window.location.pathname.endsWith('/notifications/token')) {
  window.history.replaceState(null, '', '/cli-permission/admin/notifications');
}

// Preserve the current form when a normal console action fails (including expired CSRF).
document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!form.matches('form[method="post"]') || form.hasAttribute('data-token-form') ||
      !form.action.includes('/admin/notifications/')) return;
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  if (submit.disabled) return;
  const data = new FormData(form);
  submit.disabled = true;
  const label = submit.textContent;
  submit.textContent = '正在提交…';
  try {
    const response = await fetch(form.action, {method: 'POST', body: data});
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (!response.ok) throw new Error(html.querySelector('[role="alert"]')?.textContent || '操作未完成，请刷新页面后核对状态。');
    const main = html.querySelector('#main');
    if (!main) throw new Error('登录已过期，请重新登录后重试。');
    form.closest('dialog')?.close();
    clearNotificationToken();
    document.querySelector('#main').replaceWith(main);
    window.history.replaceState(null, '', response.url);
    const feedback = main.querySelector('[role="status"]');
    if (feedback) { feedback.tabIndex = -1; feedback.focus(); feedback.scrollIntoView({block: 'nearest'}); }
  } catch (error) {
    const dialogError = form.closest('dialog')?.querySelector('[role="alert"]');
    const message = dialogError || document.querySelector('[data-notification-error]');
    message.textContent = error.message || '连接中断，请刷新核对操作是否已完成。';
    message.hidden = false;
    message.tabIndex = -1;
    message.focus();
    message.scrollIntoView({block: 'nearest'});
  } finally {
    submit.disabled = false;
    submit.textContent = label;
  }
});
