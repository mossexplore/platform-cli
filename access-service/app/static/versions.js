'use strict';
// Creating and editing share the same two-step preview and server-side validation.
const policyForm = document.querySelector('[data-version-editor]');
if (policyForm) {
  const createAction = policyForm.action;
  const title = policyForm.querySelector('#policy-create-title');
  const fields = policyForm.querySelector('[data-policy-fields]');
  const preview = policyForm.querySelector('[data-policy-preview]');
  const submit = policyForm.querySelector('[data-policy-submit]');
  const back = policyForm.querySelector('[data-policy-back]');
  const cancel = policyForm.querySelector('[data-policy-cancel]');
  const error = policyForm.querySelector('.form-error');
  let stage = 'preview';
  let busy = false;
  let editing = false;
  const submitLabel = () => stage === 'publish'
    ? (editing ? '确认保存策略' : '确认发布策略') : '下一步：预览影响';
  const changeStage = (next) => {
    stage = next;
    fields.hidden = next === 'publish';
    preview.hidden = next !== 'publish';
    back.hidden = next !== 'publish';
    cancel.hidden = next === 'publish';
    policyForm.elements.intent.value = next;
    submit.textContent = submitLabel();
    policyForm.querySelector('[data-version-step="2"]').textContent = editing ? '2 预览并保存' : '2 预览并发布';
    policyForm.querySelectorAll('[data-version-step]').forEach((step) => {
      if (step.dataset.versionStep === (next === 'publish' ? '2' : '1')) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    });
    policyForm.querySelector('.drawer-body').scrollTop = 0;
  };
  back.addEventListener('click', () => { if (!busy) { changeStage('preview'); policyForm.elements.name.focus(); } });
  const scope = policyForm.querySelector('[data-policy-environment]');
  const business = policyForm.querySelector('[data-policy-business]');
  const syncScope = () => { business.disabled = !scope.value; };
  scope.addEventListener('change', syncScope);
  syncScope();
  const mode = policyForm.querySelector('[data-policy-mode]');
  const syncMode = () => { policyForm.querySelector('[data-mode-help]').textContent = {
    observe:'记录版本判断，不提醒、不拒绝，适合首次接入。',
    warn:'提示用户升级，仍允许通过版本检查。',
    enforce:'拒绝低于最低版本、已禁用或格式不合法的版本。'
  }[mode.value]; };
  mode.addEventListener('change', syncMode);
  policyForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    busy = true;
    submit.disabled = true;
    back.disabled = true;
    error.hidden = true;
    submit.textContent = stage === 'publish' ? '正在发布…' : '正在计算影响…';
    try {
      const response = await fetch(policyForm.action, {method:'POST', body:new FormData(policyForm), headers:{Accept:'application/json'}});
      if (response.redirected) {
        if (response.url.includes('/login')) throw new Error('登录已过期，请重新登录后提交。已填写内容保留在当前页面。');
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) {
        const html = new DOMParser().parseFromString(await response.text(), 'text/html');
        throw new Error(html.querySelector('[role="alert"]')?.textContent || '提交未完成，请检查填写内容。');
      }
      const result = await response.json();
      if (typeof result.preview_html !== 'string') throw new Error('预览结果不完整，请重试。');
      preview.innerHTML = result.preview_html; // Same-origin, autoescaped Jinja fragment.
      changeStage('publish');
    } catch (err) {
      error.textContent = err.message === 'Failed to fetch' ? '连接中断，已填写内容已保留；重试前请核对是否已发布。' : err.message;
      error.hidden = false;
      error.tabIndex = -1;
      error.focus();
      error.scrollIntoView({block:'nearest'});
    } finally {
      busy = false;
      submit.disabled = false;
      back.disabled = false;
      submit.textContent = submitLabel();
      if (error.hidden && stage === 'publish') submit.focus();
    }
  });
  // Reopening starts at the fields, preserving unfinished inputs for review.
  policyForm.closest('dialog').addEventListener('close', () => {
    if (!busy) {
      changeStage('preview');
      if (editing) {
        editing = false;
        policyForm.action = createAction;
        title.textContent = '新增版本策略';
        policyForm.reset();
        syncScope(); syncMode();
      }
    }
  });
  const openWithValues = (button, values, policyId) => {
    policyForm.reset();
    editing = policyId !== null;
    policyForm.action = editing ? `${createAction}/${policyId}` : createAction;
    title.textContent = editing ? '编辑版本策略' : '新增版本策略';
    for (const [key,value] of Object.entries(values)) if (policyForm.elements[key]) policyForm.elements[key].value = value;
    changeStage('preview'); syncScope(); syncMode(); error.hidden = true;
    button.closest('dialog')?.close();
    policyForm.closest('dialog').showModal();
    policyForm.elements.name.focus();
  };
  document.querySelectorAll('[data-edit-policy]').forEach((button) => button.addEventListener('click', () => {
    openWithValues(button, JSON.parse(button.dataset.editPolicy), button.dataset.policyId);
  }));
  document.querySelectorAll('[data-copy-policy]').forEach((button) => button.addEventListener('click', () => {
    const values = JSON.parse(button.dataset.copyPolicy);
    openWithValues(button, {...values, name:(values.name + '（副本）').slice(0,128)}, null);
  }));
}
const exceptionPolicy = document.querySelector('[data-exception-policy]');
if (exceptionPolicy) exceptionPolicy.addEventListener('change', () => {
  const option = exceptionPolicy.selectedOptions[0];
  const form = exceptionPolicy.form;
  form.elements.environment.value = option.dataset.environment || '';
  form.elements.business_id.value = option.dataset.business || '';
});
