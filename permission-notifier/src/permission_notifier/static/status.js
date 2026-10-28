'use strict';
// Shared presentation rules. Labels remain visible so color is never the only cue.
(function(root){
  const deliveryTones={accepted:'positive',failed:'negative',uncertain:'warning',retry_wait:'warning',sending:'info',pending:'info',skipped:'neutral'};
  function automatic(s){
    if(s.stopping)return {text:'正在退出',tone:'warning'};
    if(!s.worker_alive)return {text:'工作线程异常',tone:'negative'};
    if(s.paused)return {text:'已暂停',tone:'warning'};
    if(!s.config_ready)return {text:'配置未完成',tone:'warning'};
    if(s.error)return {text:'需要处理',tone:'negative'};
    if(s.connection_state!=='connected')return {text:'等待连接',tone:'warning'};
    if(s.sending)return {text:'正在发送',tone:'info'};
    return {text:'自动通知已开启',tone:'positive'};
  }
  const rules={automatic,deliveryTone:state=>deliveryTones[state]||'neutral'};
  if(typeof module!=='undefined'&&module.exports)module.exports=rules;
  else root.NotifierStatus=rules;
})(typeof window!=='undefined'?window:globalThis);
