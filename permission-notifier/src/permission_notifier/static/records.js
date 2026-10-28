'use strict';
let recordsPage=1,recordsPages=1,recordsRequest=0;
let recordFilters={start:'',end:'',source:''};
async function refreshRecords(){
  const request=++recordsRequest;
  try{
    const params=new URLSearchParams({...recordFilters,page:String(recordsPage),page_size:'10'});
    const data=await api('records?'+params);
    if(request!==recordsRequest)return;
    recordsPage=data.page;recordsPages=data.pages;
    $('record-notice').textContent='';$('record-rows').replaceChildren();
    for(const record of data.items){
      const tr=document.createElement('tr');
      for(const value of [record.task_id,record.sent_at?time(record.sent_at):'未知（旧记录）',record.source==='permission'?'权限系统':'接口测试',record.uid,record.content]){
        const td=document.createElement('td');td.textContent=value;tr.append(td);
      }
      const state=document.createElement('td'),badge=document.createElement('span');
      badge.className='state-badge '+NotifierStatus.deliveryTone(record.state);badge.textContent=labels[record.state]||record.state;state.append(badge);tr.append(state);
      const actions=document.createElement('td');
      if(record.actionable){
        for(const [operation,label] of [['retry','重试'],['confirm','确认已发送'],['skip','跳过']]){
          const button=document.createElement('button');button.type='button';button.textContent=label;
          button.onclick=action(async()=>{
            if(!confirm(label+'：'+record.uid+'？不确定结果重试可能重复发送，请先核对。'))return;
            await api('tasks/'+encodeURIComponent(record.task_id)+'/resolve',{delivery_id:record.delivery_id,action:operation,confirmation:'confirm'});
            await refreshRecords();
          });actions.append(button);
        }
      }
      if(record.can_migrate){
        const button=document.createElement('button');button.type='button';button.textContent='迁移消息接口';
        button.onclick=action(async()=>{if(!confirm('迁移未完成项到当前消息接口？请先核对不确定结果。'))return;await api('tasks/'+encodeURIComponent(record.task_id)+'/resolve',{action:'migrate_route',confirmation:'confirm'});await refreshRecords();});actions.append(button);
      }
      if(!actions.children.length)actions.textContent='—';tr.append(actions);$('record-rows').append(tr);
    }
    if(!data.items.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=7;td.textContent='暂无符合条件的发送记录';td.className='empty';tr.append(td);$('record-rows').append(tr);}
    $('record-total').textContent='共 '+data.total+' 条 · 每页 10 条';$('record-page').textContent='第 '+data.page+' / '+data.pages+' 页';
    $('record-prev').disabled=data.page<=1;$('record-next').disabled=data.page>=data.pages;
  }catch(e){
    if(request!==recordsRequest)return;
    $('record-notice').className='connection-result negative';$('record-notice').textContent=e.message;
  }
}
function initRecords(){
  $('record-filters').onsubmit=event=>{event.preventDefault();recordsPage=1;recordFilters={start:$('record-start').value,end:$('record-end').value,source:$('record-source').value};refreshRecords();};
  $('record-reset').onclick=()=>{$('record-filters').reset();recordsPage=1;recordFilters={start:'',end:'',source:''};refreshRecords();};
  $('record-prev').onclick=()=>{if(recordsPage>1){recordsPage--;refreshRecords();}};
  $('record-next').onclick=()=>{if(recordsPage<recordsPages){recordsPage++;refreshRecords();}};
}
