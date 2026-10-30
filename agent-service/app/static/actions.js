import { state, post, text, notice, $ } from './api.js';

export function showAction(body, runId, data) {
  const card = text('section', '', 'action-confirmation');
  card.dataset.actionId = data.action_id;
  card.append(text('strong', '请确认操作：' + data.name));
  card.append(text('p', '环境：' + state.session.environment_id + '；业务：' + data.business.businessId));
  card.append(text('pre', JSON.stringify({arguments: data.arguments, details: data.details}, null, 2)));
  const approve = text('button', '确认执行'), reject = text('button', '拒绝');
  const result = text('p', '确认仅对本次显示的参数有效；执行中断后请先核对远端状态。');
  card.append(approve, reject, result);
  for (const [button, approved] of [[approve, true], [reject, false]]) {
    button.type = 'button';
    button.onclick = async () => {
      approve.disabled = reject.disabled = true;
      try {
        await post('/runs/' + runId + '/actions/' + data.action_id, { approved });
        result.textContent = approved ? '已确认，等待执行结果' : '已拒绝';
      } catch (error) { result.textContent = error.message; }
    };
  }
  body.append(card);
}

export function settleAction(body, data) {
  for (const card of body.querySelectorAll('.action-confirmation')) {
    if (card.dataset.actionId !== data.action_id) continue;
    for (const button of card.querySelectorAll('button')) button.disabled = true;
    card.append(text('p', data.approved ? '本次操作已确认' : '本次操作已拒绝'));
  }
}

export function installUpload() {
  const input = document.createElement('input');
  input.type = 'file';
  input.setAttribute('aria-label', '上传工具使用的附件（最多 20 MiB）');
  input.id = 'artifact-upload';
  $('prompt').parentElement.append(input);
  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { notice('附件不能超过 20 MiB'); return; }
    if (state.busy || state.session?.status !== 'ready') { notice('请完成登录和业务选择，并等待当前操作结束'); return; }
    input.disabled = true;
    try {
      const response = await fetch('/api/artifacts?name=' + encodeURIComponent(file.name), {
        method: 'POST', credentials: 'same-origin', headers: {'X-Agent-CSRF': state.session.csrf_token}, body: file,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || '上传失败');
      $('prompt').value += '\n附件 ' + data.name + '，artifact_id=' + data.artifact_id;
      notice('附件已上传，请说明如何使用');
    } catch (error) { notice(error.message); }
    finally { input.disabled = false; input.value = ''; }
  };
}
