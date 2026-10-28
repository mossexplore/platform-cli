'use strict';
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
let revision = 0, current = null, stopping = false;
const labels = {pending:'待发送',sending:'发送中',accepted:'接口已接受',retry_wait:'等待重试',failed:'失败',uncertain:'结果不确定',skipped:'已跳过'};
const time = value => value ? new Date(value*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '—';
function notice(text) { $('notice').textContent = text; }
async function api(path, body, method='POST') {
  const response = await fetch('/api/'+path, {method:body===undefined?'GET':method,
    headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},
    body:body===undefined?undefined:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.detail || '操作失败'); return data;
}
function action(fn) { return async event => { if(event)event.preventDefault(); try{await fn();}catch(e){notice(e.message);} }; }
function receiverRow(r={uid:'',label:'',enabled:true}) {
  const tr=document.createElement('tr');
  for (const [key,type] of [['enabled','checkbox'],['label','text'],['uid','text'],['test','checkbox']]) {
    const td=document.createElement('td'),input=document.createElement('input');input.type=type;input.dataset.field=key;
    input.setAttribute('aria-label',key==='uid'?'接收 UID':key==='label'?'备注':key==='test'?'选中测试':'启用对象');
    if(type==='checkbox')input.checked=key==='enabled'?r.enabled:false;else input.value=r[key]||'';td.append(input);tr.append(td);
  }
  const td=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.textContent='删除';remove.onclick=()=>tr.remove();td.append(remove);tr.append(td);$('receivers').append(tr);
}
function networkFields() {
  $('network-fields').replaceChildren();
  for(const [key,title] of [['service','权限系统'],['message','消息接口']]) {
    const group=document.createElement('div'),h=document.createElement('h3');h.textContent=title;group.append(h);
    const values=key==='service'?current.service_network:current.message.network;
    for(const [field,title,type] of [['proxy','代理地址','text'],['ca_file','CA 文件绝对路径','text'],['trust_env','使用当前用户代理环境','checkbox']]) {
      const label=document.createElement('label'),input=document.createElement('input');label.append(document.createTextNode(title));input.id=key+'-'+field;input.type=type;
      if(type==='checkbox')input.checked=values[field];else input.value=values[field];label.append(input);group.append(label);
    }$('network-fields').append(group);
  }
}
async function load() {
  const data=await api('config');current=data.config;revision=data.config_revision;
  $('service-url').value=current.permission_service_url;$('message-url').value=current.message.url;$('sender').value=current.message.sender;
  $('poll').value=current.poll_interval_seconds;$('timeout').value=current.message_timeout_seconds;
  $('token').value='';$('auth').value='';$('clear-token').checked=false;$('clear-auth').checked=false;
  $('token-state').textContent=data.secrets_configured.assistant_token?'（已配置）':'（未配置）';$('auth-state').textContent=data.secrets_configured.auth?'（已配置）':'（未配置）';
  $('receivers').replaceChildren();current.message.receivers.forEach(receiverRow);networkFields();$('revision').textContent='配置已保存';
  $('config-summary').textContent=[['权限系统地址',!!current.permission_service_url],['助手 Token',data.secrets_configured.assistant_token],['消息地址',!!current.message.url],['消息 auth',data.secrets_configured.auth],['启用接收对象',current.message.receivers.some(r=>r.enabled)]].map(([name,ok])=>name+'：'+(ok?'已配置':'未配置')).join('　 ·　 ');
}
function form() {
  const config=structuredClone(current);config.permission_service_url=$('service-url').value;config.message.url=$('message-url').value;config.message.sender=$('sender').value;
  config.poll_interval_seconds=Number($('poll').value);config.message_timeout_seconds=Number($('timeout').value);
  config.message.receivers=Array.from($('receivers').children).map(tr=>({uid:tr.querySelector('[data-field=uid]').value,label:tr.querySelector('[data-field=label]').value,enabled:tr.querySelector('[data-field=enabled]').checked}));
  for(const key of ['service','message']) {const value={proxy:$(key+'-proxy').value,ca_file:$(key+'-ca_file').value,trust_env:$(key+'-trust_env').checked};if(key==='service')config.service_network=value;else config.message.network=value;}
  const secret=(id,clear)=>$(clear).checked?{action:'clear'}:$(id).value?{action:'replace',value:$(id).value}:{action:'retain'};
  return {config_revision:revision,config,secrets:{assistant_token:secret('token','clear-token'),auth:secret('auth','clear-auth')}};
}
async function refresh() {
  if(stopping)return;
  try {
    const s=await api('status');
    $('local-state').textContent=s.worker_alive?'运行正常':'工作线程未运行';
    $('service-state').textContent={connected:'已连接',disconnected:'连接异常或已过期',unconfigured:'未配置',pending:'等待连接'}[s.connection_state];
    $('delivery-state').textContent=s.paused?'已暂停':!s.config_ready?'配置未完成':s.error?'需要处理':s.connection_state!=='connected'?'等待连接':'自动通知已开启';
    $('pause').disabled=s.paused;$('resume').disabled=!s.paused||!s.config_ready;
    $('status').textContent=`${s.worker_alive?'工作线程运行中':'工作线程尚未运行或异常'} · ${s.paused?'已暂停':'运行中'}${s.sending?' · 正在发送':''}\n最近轮询：${time(s.last_poll)}　最近连接：${time(s.last_heartbeat)}\n最近成功：${time(s.last_success_at)}　待回传：${s.pending_reports}　需处理：${s.needs_attention}\n${s.error?'提示：'+s.error:''}${s.pending_fields.length?'\n配置等待切换：'+s.pending_fields.join('、'):''}`;
    $('test-results').replaceChildren();
    if(s.tests_waiting) $('test-results').textContent='测试排队中：'+s.tests_waiting+' 个对象';
    for(const r of s.test_results) {
      const box=document.createElement('div');box.className='task';
      const d=r.diagnostic||{};
      box.textContent=`${r.uid}：${labels[r.state]||r.state}${r.http_status?' HTTP '+r.http_status:''} ${r.error_code||''}\n测试时间：${time(r.tested_at)}\n${d.method||'POST'} ${d.target_origin||''} ${d.elapsed_ms===undefined?'':'耗时 '+d.elapsed_ms+' ms'}\n${d.reason||''}\n响应体（脱敏）：${d.response_summary||'未收到可用响应'}${r.state==='accepted'?'\nHTTP 200 已判成功。如未收到，请用 UID、测试时间和响应流水号查询消息服务投递日志。':''}`;
      $('test-results').append(box);
    }
    if(s.token_expires_at){const expiry=new Date(s.token_expires_at);$('status').textContent+='\n助手 Token 到期：'+expiry.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})+(expiry-Date.now()<7*86400000?'（即将到期，请重置）':'');}
    const tasks=await api('tasks');$('tasks').replaceChildren();
    for(const task of tasks) {
      const div=document.createElement('div');div.className='task';const title=document.createElement('strong');title.textContent='任务 '+task.id;div.append(title);
      for(const [id,item] of Object.entries(task.deliveries)) {
        const row=document.createElement('p');row.append(document.createTextNode(`${item.label||item.uid}（${item.uid}）：${labels[item.state]||item.state} ${item.error_code||''} `));
        if(['failed','uncertain','retry_wait','pending'].includes(item.state))for(const [operation,label] of [['retry','重试此对象'],['confirm','确认已发送'],['skip','取消此对象']]) {
          const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=action(async()=>{if(!confirm(`${label}：${item.uid}？不确定项重发可能造成重复消息。`))return;await api('tasks/'+task.id+'/resolve',{delivery_id:id,action:operation,confirmation:'confirm'});await refresh();});row.append(button);
        }div.append(row);
      }
      if(!task.closed){const button=document.createElement('button');button.textContent='将未完成项迁移到当前消息接口';button.onclick=action(async()=>{if(confirm('确认迁移当前任务的接口？成功项不会重发，不确定项需先核对。'))await api('tasks/'+task.id+'/resolve',{action:'migrate_route',confirmation:'confirm'});});div.append(button);}
      $('tasks').append(div);
    }
    if(!tasks.length)$('tasks').textContent='暂无本地发送记录';
  } catch(e) { $('local-state').textContent='无法连接';$('service-state').textContent='状态未知';$('delivery-state').textContent='状态未知'; $('status').textContent='无法连接助手。请检查托盘或重新启动。'; }
}
$('config-form').onsubmit=action(async()=>{const result=await api('config',form(),'PUT');await load();notice(result.apply_state==='applied'?'已保存并应用；接口可用性请另行检查。':result.apply_state==='waiting_request'?'已保存，当前请求完成后应用。':'已保存，旧任务未完成，权限系统切换正在等待处理。');});
$('add-receiver').onclick=()=>receiverRow();$('reload').onclick=action(load);
$('bind').onclick=action(async()=>{await api('bind',{});notice('助手 Token 已绑定。');});
$('check').onclick=action(async()=>{const result=await api('check',form());notice('当前表单检查：'+result.message);});
$('test-message').onclick=action(async()=>{const body=form();body.uids=Array.from($('receivers').children).filter(tr=>tr.querySelector('[data-field=test]').checked).map(tr=>tr.querySelector('[data-field=uid]').value.trim());if(!body.uids.length)throw new Error('请勾选测试对象');if(!confirm('将使用当前表单（可能未保存）实际发送测试消息给：'+body.uids.join('、')))return;await api('test-message',body);notice('测试已排队，尚未确认发送；请查看下方测试结果。测试不依赖权限系统连接，不会保存表单配置。');await refresh();});
for(const id of ['pause','resume'])$(id).onclick=action(async()=>{await api(id,{});await refresh();});
$('shutdown').onclick=action(async()=>{if(!confirm('退出后将停止发送，本地网页也将关闭。继续？'))return;await api('shutdown',{});stopping=true;notice('正在退出助手，在途请求将收尾并保存。');});
$('config-form').addEventListener('input',()=>{$('revision').textContent='有未保存的修改';});
action(load)();refresh();setInterval(refresh,5000);
