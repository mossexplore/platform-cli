'use strict';
// Native dialogs keep focus within the editor and restore it to the trigger.
document.addEventListener('click', (event) => {
  const open = event.target.closest('[data-open]');
  if (open) document.getElementById(open.dataset.open)?.showModal();
  if (event.target.closest('[data-close]')) event.target.closest('dialog')?.close();
});
document.querySelectorAll('[data-editor]').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const error = form.querySelector('.form-error');
    error.hidden = true;
    const data = new FormData(form);
    if (form.action.endsWith('/batch') && !data.getAll('environments').length) {
      error.textContent = '请至少选择一个授权环境。';
      error.hidden = false;
      error.scrollIntoView({block: 'nearest'});
      return;
    }
    const submit = form.querySelector('[type="submit"]');
    if (submit.disabled) return;
    submit.disabled = true;
    const label = submit.textContent;
    submit.textContent = '正在保存…';
    try {
      const response = await fetch(form.action, {method: 'POST', body: data});
      if (response.ok && response.redirected) {
        window.location.assign(response.url);
        return;
      }
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      error.textContent = html.querySelector('[role="alert"]')?.textContent || '保存未完成，请刷新页面后重试。';
    } catch (_) {
      error.textContent = '连接中断，请检查网络后重试。已填写内容已保留；重试前请核对是否已保存。';
    }
    error.hidden = false;
    error.scrollIntoView({block:'nearest'});
    submit.disabled = false;
    submit.textContent = label;
  });
});
