'use strict';
(() => {
  const dialog = document.querySelector('#bulk-grants');
  if (!dialog) return;
  const table = document.querySelector('.people-table');
  const toolbar = document.querySelector('[data-bulk-toolbar]');
  const openButton = toolbar.querySelector('[data-bulk-open]');
  openButton.textContent = '批量编辑';
  toolbar.prepend(openButton);
  document.querySelector('.filter-bar button').insertAdjacentElement('afterend', toolbar);
  const form = document.querySelector('#bulk-edit-form');
  const error = dialog.querySelector('.form-error');
  const saveButton = dialog.querySelector('[data-bulk-save]');
  const environmentInputs = [...form.querySelectorAll('[name="environments"]:not(:disabled)')];
  const allEnvironments = form.querySelector('[data-environments-all]');
  function updateEnvironments() {
    const count = environmentInputs.filter(input => input.checked).length;
    form.querySelector('[data-environment-count]').textContent = `已选 ${count} 个`;
    allEnvironments.checked = count > 0 && count === environmentInputs.length;
    allEnvironments.indeterminate = count > 0 && count < environmentInputs.length;
    allEnvironments.disabled = environmentInputs.length === 0;
    saveButton.disabled = busy || selected.size === 0;
  }
  const filters = new URLSearchParams(location.search);
  const scope = JSON.stringify(['q', 'status', 'grant_status'].map(k => filters.get(k) || ''));
  const storageKey = `bulk-grants:${dialog.dataset.actor}:${dialog.dataset.csrf}`;
  let selected = new Map();
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
    error.hidden = true;
  }
  function refresh() {
    invalidate();
    checkboxes.forEach(input => { input.checked = selected.has(Number(input.dataset.userId)); });
    const checked = checkboxes.filter(input => input.checked).length;
    all.checked = checked > 0 && checked === checkboxes.length;
    all.indeterminate = checked > 0 && checked < checkboxes.length;
    all.disabled = checkboxes.length === 0;
    toolbar.hidden = false;
    toolbar.querySelector('[data-selection-count]').textContent = `已选 ${selected.size} 人`;
    toolbar.querySelector('[data-selection-count]').hidden = selected.size === 0;
    toolbar.querySelector('[data-selection-clear]').hidden = selected.size === 0;
    toolbar.querySelector('[data-bulk-open]').disabled = selected.size === 0;
    dialog.querySelector('[data-bulk-count]').textContent = `${selected.size} 人`;
    updateEnvironments();
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
    if (event.target === allEnvironments) environmentInputs.forEach(input => { input.checked = allEnvironments.checked; });
    invalidate();
    updateEnvironments();
  });
  function payload() {
    const edits = [...form.querySelectorAll('[name="environments"]:checked')].map(input => ({
      environment_id: Number(input.value), operation: 'enable'}));
    return {csrf: dialog.dataset.csrf, user_ids: [...selected.keys()], edits, reset: true};
  }
  async function request(action, body) {
    const response = await fetch(`/cli-permission/admin/grants/bulk/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (response.ok && response.headers.get('content-type')?.includes('application/json')) return response.json();
    const html = new DOMParser().parseFromString(await response.text(), 'text/html');
    const message = html.querySelector('[role="alert"]')?.textContent || '请求未完成，请核对登录状态后重试';
    throw new Error(message.includes('预览已过期') ? '人员、环境或授权已变化，请重新点击确定授权' : message);
  }
  function setBusy(value) {
    busy = value;
    dialog.querySelectorAll('button').forEach(button => { button.disabled = value; });
    form.inert = value;
    saveButton.textContent = value ? '正在授权…' : '确定授权';
    if (!value) updateEnvironments();
  }
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  async function perform() {
    if (busy) return;
    error.hidden = true;
    try {
      const body = payload();
      setBusy(true);
      // Obtain a fresh snapshot and save without an extra confirmation step.
      const result = await request('preview', body);
      if (result.changes.length) await request('save', {...body, token: result.token});
      selected.clear(); refresh();
      location.assign('/cli-permission/admin?tab=users&saved=1');
    } catch (problem) {
      invalidate();
      error.textContent = problem.message === 'Failed to fetch' ? '连接中断，编辑内容已保留；请核对是否已保存后重试' : problem.message;
      error.hidden = false;
      error.scrollIntoView({block: 'nearest'});
    } finally { setBusy(false); }
  }
  form.addEventListener('submit', event => { event.preventDefault(); perform(); });
  refresh();
})();
