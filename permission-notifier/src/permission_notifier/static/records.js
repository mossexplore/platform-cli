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
      for(const value of [record.task_id,record.sent_at?time(record.sent_at):'未知（旧记录）',record.source==='permission'?'权限系统':'接口测试',record.uid,record.applicant_name||'-',record.applicant_account||'-',record.application_time||'-']){
        const td=document.createElement('td');td.textContent=value;tr.append(td);
      }
      const state=document.createElement('td'),badge=document.createElement('span');
      badge.className='state-badge '+NotifierStatus.deliveryTone(record.state);badge.textContent=labels[record.state]||record.state;state.append(badge);tr.append(state);
      $('record-rows').append(tr);
    }
    if(!data.items.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=8;td.textContent='暂无符合条件的发送记录';td.className='empty';tr.append(td);$('record-rows').append(tr);}
    $('record-total').textContent='共 '+data.total+' 条 · 每页 10 条';$('record-page').textContent='第 '+data.page+' / '+data.pages+' 页';
    $('record-prev').disabled=data.page<=1;$('record-next').disabled=data.page>=data.pages;
  }catch(e){
    if(request!==recordsRequest)return;
    $('record-notice').className='connection-result negative';$('record-notice').textContent=e.message;
  }
}
function recentRange(now=Date.now()){
  const local=value=>new Date(value+8*3600000).toISOString().slice(0,19);
  return {start:local(now-3*86400000),end:local(now),source:''};
}
function resetRecordFilters(){
  recordsPage=1;recordFilters=recentRange();
  $('record-start').value=recordFilters.start;$('record-end').value=recordFilters.end;$('record-source').value='';
}
function initRecords(){
  resetRecordFilters();
  $('record-filters').onsubmit=event=>{event.preventDefault();recordsPage=1;recordFilters={start:$('record-start').value,end:$('record-end').value,source:$('record-source').value};refreshRecords();};
  $('record-reset').onclick=()=>{resetRecordFilters();refreshRecords();};
  $('record-prev').onclick=()=>{if(recordsPage>1){recordsPage--;refreshRecords();}};
  $('record-next').onclick=()=>{if(recordsPage<recordsPages){recordsPage++;refreshRecords();}};
}

if(typeof module!=='undefined'&&module.exports)module.exports={recentRange};
