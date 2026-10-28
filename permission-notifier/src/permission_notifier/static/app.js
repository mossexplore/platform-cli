'use strict';
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
let revision = 0, current = null, stopping = false;
const labels = {pending:'待发送',sending:'发送中',accepted:'接口已接受',retry_wait:'等待重试',failed:'失败',uncertain:'结果不确定',skipped:'已跳过'};
const time = value => value ? new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value*1000)) : '—';
function notice(text,tone='info') { $('notice').textContent=text;$('notice').className='notice '+tone; }
function badge(id,text,tone){$(id).textContent=text;$(id).className='state-badge '+tone;}
async function api(path, body, method='POST') {
  const response = await fetch('/api/'+path, {method:body===undefined?'GET':method,
    headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},
    body:body===undefined?undefined:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.detail || '操作失败'); return data;
}
function action(fn) { return async event => { if(event)event.preventDefault(); try{await fn();}catch(e){notice(e.message,'negative');} }; }
function receiverRow(r={uid:'',label:'',enabled:true}) {
  const tr=document.createElement('tr');
  for (const [key,type] of [['enabled','checkbox'],['label','text'],['uid','text']]) {
    const td=document.createElement('td'),input=document.createElement('input');input.type=type;input.dataset.field=key;
    input.setAttribute('aria-label',key==='uid'?'接收 UID':key==='label'?'备注':key==='test'?'选中测试':'启用对象');
    if(type==='checkbox')input.checked=key==='enabled'?r.enabled:false;else input.value=r[key]||'';td.append(input);tr.append(td);
  }
  const td=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.className='danger';remove.textContent='删除';remove.onclick=()=>{tr.remove();markDirty();updateTestReceivers();};td.append(remove);tr.append(td);$('receivers').append(tr);updateTestReceivers();
}
async function load() {
  const data=await api('config');current=data.config;revision=data.config_revision;
  $('service-url').value=current.permission_service_url;$('message-url').value=current.message.url;$('sender').value=current.message.sender;
  $('poll').value=current.poll_interval_seconds;$('timeout').value=current.message_timeout_seconds;
  for(const [id,key] of [['token','assistant_token'],['auth','auth']]) {
    const input=$(id),configured=data.secrets_configured[key];
    input.value=configured?'****':'';
    input.dataset.masked=configured?'true':'false';
    input.placeholder=configured?'已保存；输入新值可替换':'请输入凭据';
  }
  checkResult('尚未检查');
  $('clear-token').checked=false;$('clear-auth').checked=false;
  for(const [id,configured] of [['token-state',data.secrets_configured.assistant_token],['auth-state',data.secrets_configured.auth]])badge(id,configured?'已配置':'未配置',configured?'positive':'neutral');
  $('receivers').replaceChildren();current.message.receivers.forEach(receiverRow);$('revision').textContent='配置已保存';
  $('message-config-state').textContent=current.message.url&&data.secrets_configured.auth?'已配置':'待配置';
  $('revision').className='save-state positive';
  $('message-config-state').dataset.ready=String(!!(current.message.url&&data.secrets_configured.auth));
  $('config-summary').replaceChildren();
  for(const [name,ok] of [['权限系统地址',!!current.permission_service_url],['助手 Token',data.secrets_configured.assistant_token],['消息地址',!!current.message.url],['消息 auth',data.secrets_configured.auth],['启用接收对象',current.message.receivers.some(r=>r.enabled)]]) {
    const row=document.createElement('div'),label=document.createElement('span'),badge=document.createElement('span');
    row.className='config-summary-row';label.textContent=name;
    badge.className='state-badge '+(ok?'positive':'neutral');badge.textContent=ok?'已配置':'未配置';
    row.append(label,badge);$('config-summary').append(row);
  }
}
function form() {
  const config=structuredClone(current);config.permission_service_url=$('service-url').value;config.message.url=$('message-url').value;config.message.sender=$('sender').value;
  config.poll_interval_seconds=Number($('poll').value);config.message_timeout_seconds=Number($('timeout').value);
  config.message.receivers=Array.from($('receivers').children).map(tr=>({uid:tr.querySelector('[data-field=uid]').value,label:tr.querySelector('[data-field=label]').value,enabled:tr.querySelector('[data-field=enabled]').checked}));
  const secret=(id,clear)=>$(clear).checked?{action:'clear'}:$(id).dataset.masked!=='true'&&$(id).value?{action:'replace',value:$(id).value}:{action:'retain'};
  return {config_revision:revision,config,secrets:{assistant_token:secret('token','clear-token'),auth:secret('auth','clear-auth')}};
}
async function refresh() {
  if(stopping)return;
  try {
    const s=await api('status');
    badge('local-state',s.worker_alive?'运行正常':'工作线程未运行',s.worker_alive?'positive':'negative');
    badge('service-state',{connected:'已连接',disconnected:'连接异常或已过期',unconfigured:'未配置',pending:'等待连接'}[s.connection_state]||'状态未知',s.connection_state==='connected'?'positive':s.connection_state==='disconnected'?'negative':'neutral');
    const automatic=NotifierStatus.automatic(s);badge('delivery-state',automatic.text,automatic.tone);
    $('pause').disabled=s.paused;$('resume').disabled=!s.paused||!s.config_ready;
    $('worker-state').textContent=s.worker_alive?'运行中':'未运行或异常';
    $('worker-state').className='state-badge '+(s.worker_alive?'positive':'negative');
    badge('notification-state',automatic.text,automatic.tone);
    const alerts=[];
    if(s.error)alerts.push('提示：'+s.error);
    if(s.needs_attention)alerts.push('需处理：'+s.needs_attention+' 个发送结果');
    if(s.pending_fields.length)alerts.push('配置等待切换：'+s.pending_fields.join('、'));
    $('runtime-alert').hidden=!alerts.length;
    $('runtime-alert').textContent=alerts.join('\n');
    $('runtime-alert').className='connection-result '+(s.error&&!['UNCONFIGURED','SUCCESS_RULE_OR_CONFIG_REQUIRED'].includes(s.error)?'negative':'warning');
    $('status').textContent=`最近轮询：${time(s.last_poll)}\n最近连接：${time(s.last_heartbeat)}\n最近成功：${time(s.last_success_at)}\n待回传：${s.pending_reports}　需处理：${s.needs_attention}`;
    $('test-message').disabled=s.sending||s.tests_waiting>0;
    $('test-message').textContent=s.sending?'发送处理中…':s.tests_waiting?'测试排队中…':'发送测试通知';
    $('test-results').replaceChildren();
    if(!s.test_results.length&&!s.tests_waiting)$('test-results').textContent='尚未发送测试通知';

    if(s.error==='TOKEN_EXPIRED')badge('service-state','Token 已过期','negative');
    if(s.error==='SERVICE_PROXY_ERROR')badge('service-state','代理连接异常','negative');
    if(s.tests_waiting){const waiting=document.createElement('p');waiting.className='result-heading info';waiting.textContent='测试排队中：'+s.tests_waiting+' 个对象';$('test-results').append(waiting);}
    for(const r of s.test_results) {
      const box=document.createElement('div');box.className='task';
      const d=r.diagnostic||{};
      const heading=document.createElement('strong');heading.className='result-heading '+NotifierStatus.deliveryTone(r.state);
      heading.textContent=`${r.uid} · ${labels[r.state]||r.state}${r.http_status?' · HTTP '+r.http_status:''}`;
      const meta=document.createElement('p');meta.className='result-meta';
      meta.textContent=`${time(r.tested_at)}${d.elapsed_ms===undefined?'':' · '+d.elapsed_ms+' ms'}\n${d.method||'POST'} ${d.target_origin||''} ${r.error_code||''} ${d.reason||''}`;
      const title=document.createElement('h3');title.textContent='响应体（脱敏）';
      const response=document.createElement('pre');response.textContent=d.response_summary||'未收到可用响应';
      box.append(heading,meta,title,response);
      $('test-results').append(box);
    }
    if(s.token_expires_at){const expiry=new Date(s.token_expires_at);$('status').textContent+='\n助手 Token 到期：'+expiry.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+(expiry-Date.now()<7*86400000?'（即将到期，请重置）':'');}
    const tasks=await api('tasks');$('tasks').replaceChildren();
    for(const task of tasks) {
      const div=document.createElement('div');div.className='task';const title=document.createElement('strong');title.textContent='任务 '+task.id;div.append(title);
      for(const [id,item] of Object.entries(task.deliveries)) {
        const row=document.createElement('p'),state=document.createElement('span');state.className='state-badge '+NotifierStatus.deliveryTone(item.state);state.textContent=labels[item.state]||item.state;row.append(document.createTextNode(`${item.label||item.uid}（${item.uid}）：`),state,document.createTextNode(' '+(item.error_code||'')+' '));
        if(['failed','uncertain','retry_wait','pending'].includes(item.state))for(const [operation,label] of [['retry','重试此对象'],['confirm','确认已发送'],['skip','取消此对象']]) {
          const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=action(async()=>{if(!confirm(`${label}：${item.uid}？不确定项重发可能造成重复消息。`))return;await api('tasks/'+task.id+'/resolve',{delivery_id:id,action:operation,confirmation:'confirm'});await refresh();});row.append(button);
        }div.append(row);
      }
      if(!task.closed){const button=document.createElement('button');button.textContent='将未完成项迁移到当前消息接口';button.onclick=action(async()=>{if(confirm('确认迁移当前任务的接口？成功项不会重发，不确定项需先核对。'))await api('tasks/'+task.id+'/resolve',{action:'migrate_route',confirmation:'confirm'});});div.append(button);}
      $('tasks').append(div);
    }
    if(!tasks.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='暂无本地发送记录';$('tasks').append(empty);}
  } catch(e) { $('runtime-alert').hidden=true;badge('local-state','无法连接','negative');badge('service-state','状态未知','neutral');badge('delivery-state','状态未知','neutral'); $('worker-state').textContent='状态未知';$('worker-state').className='state-badge neutral';$('notification-state').textContent='状态未知';$('notification-state').className='state-badge neutral';$('status').textContent='无法连接助手。请检查托盘或重新启动。'; }
}
$('config-form').onsubmit=action(async()=>{const result=await api('config',form(),'PUT');await load();notice(result.apply_state==='applied'?'已保存并应用；接口可用性请另行检查。':result.apply_state==='waiting_request'?'已保存，当前请求完成后应用。':'已保存，旧任务未完成，权限系统切换正在等待处理。',result.apply_state==='applied'?'positive':'warning');});
$('add-receiver').onclick=()=>{receiverRow();markDirty();};$('reload').onclick=action(async()=>{if($('revision').classList.contains('dirty')&&!confirm('放弃未保存的修改并重新加载？'))return;await load();});
$('bind').onclick=action(async()=>{await api('bind',{});notice('助手 Token 已绑定。','positive');});
function checkResult(message,tone='neutral'){
  $('check-result').textContent=message;
  $('check-result').className='connection-result '+tone;
}
$('check').onclick=action(async()=>{
  if(!$('service-url').value){checkResult('请先填写权限系统服务地址','warning');throw new Error('请先填写权限系统服务地址');}
  checkResult('正在检查…');$('check').disabled=true;
  const checkedForm=form();
  try{const result=await api('check',checkedForm);if(JSON.stringify(form())!==JSON.stringify(checkedForm)){checkResult('配置已修改，请重新检查');return;}checkResult(result.message,'positive');}
  catch(e){checkResult(e.message,'negative');throw e;}
  finally{$('check').disabled=false;}
});
$('test-message').onclick=action(async()=>{const body=form();body.uids=Array.from($('test-receivers').selectedOptions).map(option=>option.value);if(!body.uids.length)throw new Error('请先在测试与诊断页签添加并启用对象，再选择测试接收人');if(!confirm('将使用当前表单（可能未保存）实际发送测试消息给：'+body.uids.join('、')))return;await api('test-message',body);notice('测试已排队，尚未确认发送；请查看下方测试结果。测试不依赖权限系统连接，不会保存表单配置。');await refresh();});
for(const id of ['pause','resume'])$(id).onclick=action(async()=>{await api(id,{});await refresh();});
$('shutdown').onclick=action(async()=>{if(!confirm('退出后将停止发送，本地网页也将关闭。继续？'))return;await api('shutdown',{});stopping=true;notice('正在退出助手，在途请求将收尾并保存。');});
for(const button of document.querySelectorAll('[data-replace]'))button.onclick=()=>{const input=$(button.dataset.replace);input.value='';input.dataset.masked='false';if(button.dataset.replace==='token')checkResult('连接配置已修改，请重新检查');input.focus();};
for(const id of ['token','auth']) {
  $(id).addEventListener('focus',()=>{if($(id).dataset.masked==='true')$(id).select();});
  $(id).addEventListener('input',()=>{$(id).dataset.masked='false';});
}
function markDirty(){ $('revision').textContent='有未保存的修改，请保存配置';$('revision').className='save-state warning dirty'; }
function updateTestReceivers(){
  const selected=new Set(Array.from($('test-receivers').selectedOptions).map(o=>o.value));
  $('test-receivers').replaceChildren();
  for(const tr of $('receivers').children){
    const uid=tr.querySelector('[data-field=uid]').value.trim();
    if(!uid||!tr.querySelector('[data-field=enabled]').checked)continue;
    const option=document.createElement('option');option.value=uid;
    option.textContent=(tr.querySelector('[data-field=label]').value||'接收对象')+' · '+uid;
    option.selected=selected.has(uid);$('test-receivers').append(option);
  }
  if(!selected.size&&$('test-receivers').options.length)$('test-receivers').options[0].selected=true;
}
const pageTitles={connection:['连接配置','配置与验证，一目了然'],receivers:['消息配置','管理消息接口、接收人及测试诊断'],records:['发送记录','查看发送结果，处理需要关注的通知'],advanced:['高级设置','调整通知轮询与请求超时']};
function showPage(page){
  if(page==='diagnostics'){page='receivers';showReceiverTab('diagnostics');}
  if(!pageTitles[page])page='connection';
  document.querySelectorAll('[data-view]').forEach(node=>node.hidden=node.dataset.view!==page);
  document.querySelectorAll('[data-page]').forEach(node=>{node.classList.toggle('active',node.dataset.page===page);if(node.dataset.page===page)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');});
  $('page-title').textContent=pageTitles[page][0];$('page-description').textContent=pageTitles[page][1];

  $('revision').hidden=page==='records';
}
for(const button of document.querySelectorAll('[data-page]'))button.onclick=()=>{location.hash=button.dataset.page;};
window.addEventListener('hashchange',()=>showPage(location.hash.slice(1)));
function showReceiverTab(kind){
  for(const key of ['message','diagnostics']){
    const selected=key===kind;
    $('tab-'+key).classList.toggle('active',selected);
    $('tab-'+key).setAttribute('aria-selected',String(selected));
    $('tab-'+key).tabIndex=selected?0:-1;
    $(key+'-panel').hidden=!selected;
  }
}
$('diagnostic-test-slot').append($('test-panel'));
for(const kind of ['message','diagnostics']){
  $('tab-'+kind).onclick=()=>showReceiverTab(kind);
  $('tab-'+kind).onkeydown=event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const next=event.key==='Home'?'message':event.key==='End'?'diagnostics':kind==='message'?'diagnostics':'message';
    showReceiverTab(next);$('tab-'+next).focus();
  };
}
showReceiverTab('message');
$('config-form').addEventListener('input',event=>{if(event.target.id==='test-receivers')return;markDirty();if(['service-url','token','clear-token'].includes(event.target.id))checkResult('连接配置已修改，请重新检查');if(event.target.closest('#receivers'))updateTestReceivers();});
showPage(location.hash.slice(1));
action(load)();refresh();setInterval(refresh,5000);
