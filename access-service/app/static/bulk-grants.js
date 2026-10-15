'use strict';
(() => {
  const dialog = document.querySelector('#bulk-grants');
  if (!dialog) return;
  const table = document.querySelector('.people-table');
  const toolbar = document.querySelector('[data-bulk-toolbar]');
  const form = document.querySelector('#bulk-edit-form');
  const error = dialog.querySelector('.form-error');
  const previewPanel = dialog.querySelector('[data-bulk-preview]');
  const saveButton = dialog.querySelector('[data-bulk-save]');
  const previewButton = dialog.querySelector('[data-bulk-preview-button]');
  const filters = new URLSearchParams(location.search);
  const scope = JSON.stringify(['q', 'status', 'grant_status'].map(k => filters.get(k) || ''));
  const storageKey = `bulk-grants:${dialog.dataset.actor}:${dialog.dataset.csrf}`;
  let selected = new Map();
  let token = '';
  let busy = false;
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    if (stored?.scope === scope && Array.isArray(stored.people) && stored.people.length <= 100) {
      selected = new Map(stored.people.filter(([id, name]) => Number.isInteger(id) && id > 0 && typeof name === 'string'));
    }
  } catch (_) { /* Selection remains usable when storage is unavailable. */ }
  const all = document.createElement('input');
  all.type = 'checkbox';
  all.setAttribute('aria-label', '全选当前页人员');
  const heading = document.createElement('th');
  heading.className = 'bulk-check';
  heading.append(all);
  table.tHead.rows[0].prepend(heading);
  const checkboxes = [];
  table.querySelectorAll('tbody tr[data-account]').forEach(row => {
    const edit = row.querySelector('[data-open^="account-grants-"]');
    const id = Number(edit.dataset.open.replace('account-grants-', ''));
    const cell = document.createElement('td');
    cell.className = 'bulk-check';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.dataset.userId = id;
    input.setAttribute('aria-label', `选择 ${row.dataset.account}`);
    cell.append(input);
    row.prepend(cell);
    checkboxes.push(input);
    input.addEventListener('change', () => {
      if (input.checked && selected.size >= 100 && !selected.has(id)) {
        input.checked = false;
        window.alert('每批最多选择 100 人，请拆分操作');
        return;
      }
      if (input.checked) selected.set(id, row.dataset.account);
      else selected.delete(id);
      refresh();
    });
  });
  const empty = table.querySelector('td.empty');
  if (empty) empty.colSpan = 9;
  function invalidate() {
    token = '';
    previewPanel.hidden = true;
    saveButton.hidden = true;
    saveButton.disabled = true;
  }
  function refresh() {
    invalidate();
    checkboxes.forEach(input => { input.checked = selected.has(Number(input.dataset.userId)); });
    const checked = checkboxes.filter(input => input.checked).length;
    all.checked = checked > 0 && checked === checkboxes.length;
    all.indeterminate = checked > 0 && checked < checkboxes.length;
    all.disabled = checkboxes.length === 0;
    toolbar.hidden = selected.size === 0;
    toolbar.querySelector('[data-selection-count]').textContent = `已选 ${selected.size} 人`;
    dialog.querySelector('[data-bulk-count]').textContent = `${selected.size} 人`;
    previewButton.disabled = selected.size === 0;
    const people = dialog.querySelector('[data-bulk-selected]');
    people.replaceChildren();
    selected.forEach((name, id) => {
      const item = document.createElement('span');
      item.className = 'bulk-person';
      item.append(document.createTextNode(name));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.title = `移除 ${name}`;
      remove.setAttribute('aria-label', remove.title);
      remove.addEventListener('click', () => { if (!busy) { selected.delete(id); refresh(); } });
      item.append(remove);
      people.append(item);
    });
    try { sessionStorage.setItem(storageKey, JSON.stringify({scope, people: [...selected]})); } catch (_) { /* Optional persistence. */ }
  }
  all.addEventListener('change', () => {
    const ids = checkboxes.map(input => Number(input.dataset.userId));
    if (all.checked && new Set([...selected.keys(), ...ids]).size > 100) {
      window.alert('每批最多选择 100 人，请拆分操作');
      refresh();
      return;
    }
    checkboxes.forEach(input => {
      const id = Number(input.dataset.userId);
      if (all.checked) selected.set(id, input.closest('tr').dataset.account);
      else selected.delete(id);
    });
    refresh();
  });
  toolbar.querySelector('[data-selection-clear]').addEventListener('click', () => { selected.clear(); refresh(); });
  toolbar.querySelector('[data-bulk-open]').addEventListener('click', () => { error.hidden = true; dialog.showModal(); });
  form.addEventListener('input', invalidate);
  form.addEventListener('change', event => {
    const row = event.target.closest('[data-bulk-env]');
    if (!row) return;
    const revoked = row.querySelector('[name="operation"]').value === 'revoke';
    ['expiry_mode', 'note_mode'].forEach(name => {
      const field = row.querySelector(`[name="${name}"]`);
      if (revoked) field.value = 'keep';
      field.disabled = revoked;
    });
    [['expiry_mode', 'expires_at'], ['note_mode', 'note']].forEach(([mode, name]) => {
      const field = row.querySelector(`[name="${name}"]`);
      field.hidden = revoked || row.querySelector(`[name="${mode}"]`).value !== 'set';
      field.disabled = field.hidden;
      field.required = !field.hidden;
    });
    invalidate();
  });
  function payload() {
    const edits = [...form.querySelectorAll('[data-bulk-env]')].map(row => {
      const value = name => row.querySelector(`[name="${name}"]`).value;
      return {environment_id: Number(row.dataset.bulkEnv), operation: value('operation'),
        expiry_mode: value('expiry_mode'), expires_at: value('expires_at'), note_mode: value('note_mode'), note: value('note')};
    }).filter(edit => edit.operation !== 'keep' || edit.expiry_mode !== 'keep' || edit.note_mode !== 'keep');
    if (!edits.length) throw new Error('请至少设置一项环境变更');
    return {csrf: dialog.dataset.csrf, user_ids: [...selected.keys()], edits, token};
  }
  async function request(action, body) {
    const response = await fetch(`/cli-permission/admin/grants/bulk/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (response.ok && response.headers.get('content-type')?.includes('application/json')) return response.json();
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    throw new Error(html.querySelector('[role="alert"]')?.textContent || '请求未完成，请核对登录状态后重试');
  }
  function setBusy(value) {
    busy = value;
    dialog.querySelectorAll('button').forEach(button => { button.disabled = value; });
    form.inert = value;
    if (!value) { previewButton.disabled = selected.size === 0; saveButton.disabled = !token; }
  }
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  async function perform(action) {
    if (busy) return;
    error.hidden = true;
    try {
      const body = payload();
      setBusy(true);
      const result = await request(action, body);
      if (action === 'save') {
        selected.clear(); refresh();
        location.assign('/cli-permission/admin?tab=users&saved=1');
        return;
      }
      token = result.changes.length ? result.token : '';
      const c = result.counts;
      dialog.querySelector('[data-bulk-summary]').textContent = `影响 ${result.affected_users} 人；新增 ${c.created} 项，修改 ${c.updated} 项，撤销 ${c.revoked} 项，未变化 ${c.unchanged} 项`;
      const warnings = dialog.querySelector('[data-bulk-warnings]');
      warnings.replaceChildren();
      const messages = [...result.warnings];
      if (c.revoked) messages.unshift(`本次将撤销 ${c.revoked} 项授权，请核对人员和环境`);
      if (!token) messages.push('没有实际变更，无需保存');
      messages.forEach(message => { const li = document.createElement('li'); li.textContent = message; warnings.append(li); });
      const rows = dialog.querySelector('[data-bulk-changes]');
      rows.replaceChildren();
      result.changes.forEach(change => {
        const row = document.createElement('tr');
        ['username', 'environment', 'before_text', 'after_text'].forEach(key => {
          const td = document.createElement('td'); td.textContent = change[key]; row.append(td);
        });
        rows.append(row);
      });
      previewPanel.hidden = false;
      saveButton.hidden = false;
      saveButton.textContent = `确认保存 ${result.changes.length} 项变更`;
      previewPanel.scrollIntoView({block: 'nearest'});
    } catch (problem) {
      invalidate();
      error.textContent = problem.message === 'Failed to fetch' ? '连接中断，编辑内容已保留；请核对是否已保存，再重新预览' : problem.message;
      error.hidden = false;
      error.scrollIntoView({block: 'nearest'});
    } finally { setBusy(false); }
  }
  form.addEventListener('submit', event => { event.preventDefault(); perform('preview'); });
  saveButton.addEventListener('click', () => perform('save'));
  refresh();
})();
