const {test}=require('node:test');
const assert=require('node:assert/strict');
const {automatic,deliveryTone}=require('../src/permission_notifier/static/status.js');
const running={worker_alive:true,paused:false,config_ready:true,error:'',connection_state:'connected',sending:false};
test('automatic status only shows green when all prerequisites hold',()=>{
  assert.deepEqual(automatic(running),{text:'自动通知已开启',tone:'positive'});
  for(const overrides of [{paused:true},{config_ready:false},{error:'TOKEN_EXPIRED'},
    {connection_state:'disconnected'},{worker_alive:false},{stopping:true}]){
    assert.notEqual(automatic({...running,...overrides}).tone,'positive');
  }
});
test('paused, sending, failed and unknown conditions have distinct meanings',()=>{
  assert.equal(automatic({...running,paused:true}).tone,'warning');
  assert.equal(automatic({...running,sending:true}).tone,'info');
  assert.equal(automatic({...running,error:'SERVICE_PROXY_ERROR'}).tone,'negative');
  assert.equal(automatic({...running,worker_alive:false,paused:true}).tone,'negative');
  assert.equal(automatic({...running,connection_state:'pending'}).text,'等待连接');
});
test('delivery result colors distinguish failure from uncertainty',()=>{
  for(const [state,tone] of Object.entries({accepted:'positive',failed:'negative',uncertain:'warning',
    retry_wait:'warning',pending:'info',sending:'info',skipped:'neutral',unknown:'neutral'})){
    assert.equal(deliveryTone(state),tone);
  }
});
