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
      if (response.ok && form.hasAttribute('data-credentials') && response.headers.get('content-type')?.includes('application/json')) {
        const result = await response.json();
        form.querySelector('.admin-account-fields').hidden = true;
        form.querySelector('[data-credential-text]').value = `管理员账号：${result.username}\n登录密码：${result.password}`;
        form.querySelector('.credential-result').hidden = false;
        form.closest('dialog').dataset.credentialsGenerated = 'true';
        submit.hidden = true;
        return;
      }
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

// Passwords only live in this response and dialog; no local/session storage.
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-copy-credentials]');
  if (!button) return;
  const panel = button.closest('.credential-result');
  const field = panel.querySelector('[data-credential-text]');
  const status = panel.querySelector('[data-copy-status]');
  try {
    if (!navigator.clipboard) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(field.value);
    status.textContent = '账号和密码已复制。';
  } catch (_) {
    field.focus();
    field.select();
    status.textContent = '浏览器不允许自动复制，已选中账号和密码，请按 Ctrl+C（Mac：⌘C）复制。';
  }
});
document.querySelectorAll('dialog').forEach((dialog) => {
  dialog.addEventListener('close', () => {
    if (dialog.dataset.credentialsGenerated === 'true') {
      dialog.querySelector('[data-credential-text]').value = '';
      window.location.assign('/cli-permission/admin/administrators?saved=1');
    }
  });
});

// The server independently enforces the same exact confirmation value.
document.querySelectorAll('[data-delete]').forEach((form) => {
  const input = form.querySelector('[data-delete-confirm]');
  const submit = form.querySelector('[type="submit"]');
  input.addEventListener('input', () => { submit.disabled = input.value !== 'yes'; });
  form.closest('dialog').addEventListener('close', () => {
    input.value = '';
    submit.disabled = true;
    form.querySelector('.form-error').hidden = true;
  });
});

// The backend interprets datetime-local values as Beijing time (UTC+8).
document.addEventListener('click', (event) => {
  const chip = event.target.closest('[data-preset]');
  if (!chip) return;
  const range = chip.closest('[data-time-range]');
  if (!range) return;
  const hours = {'1h': 1, '24h': 24, '7d': 168, '30d': 720}[chip.dataset.preset];
  if (!hours) return;
  const beijing = (d) => new Date(d.getTime() + 8 * 3600000).toISOString().slice(0, 19);
  const end = new Date();
  range.querySelector('[name="begin"]').value = beijing(new Date(end.getTime() - hours * 3600000));
  range.querySelector('[name="end"]').value = beijing(end);
  range.querySelectorAll('.preset-chip').forEach((c) => c.classList.toggle('active', c === chip));
});
// Typing a custom range clears the preset highlight.
document.querySelectorAll('[data-time-range] input').forEach((input) => {
  input.addEventListener('input', () => {
    input.closest('[data-time-range]').querySelectorAll('.preset-chip').forEach((c) => c.classList.remove('active'));
  });
});
