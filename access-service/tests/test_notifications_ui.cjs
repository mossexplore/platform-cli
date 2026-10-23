const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../app/static/notifications.js'),'utf8');

function harness({clipboardFails=false, errorResponse=false}={}) {
  const handlers={};
  const field={value:'one-time-test-token',defaultValue:'one-time-test-token',textContent:'one-time-test-token',focus(){this.focused=true;},select(){this.selected=true;}};
  const result={hidden:false,querySelector(){return field;}};
  const copyStatus={textContent:''};
  const error={hidden:true,textContent:'',focus(){this.focused=true;},scrollIntoView(){}};
  const submit={disabled:false,textContent:'保存设置'};
  const form={action:'http://localhost/cli-permission/admin/notifications/enabled',
    matches(){return true;},hasAttribute(){return false;},closest(){return null;},
    querySelector(){return submit;}};
  const document={
    addEventListener(type,handler){(handlers[type]??=[]).push(handler);},
    querySelector(selector){return ({'[data-token-result]':result,'[data-token-result] textarea':field,
      '[data-token-copy-status]':copyStatus,'[data-notification-error]':error})[selector];},
  };
  const window={location:{pathname:'/cli-permission/admin/notifications'},
    addEventListener(type,handler){handlers[type]=[handler];},history:{replaceState(){throw Error('must not navigate on failure');}}};
  const context={document,window,navigator:{clipboard:{async writeText(value){if(clipboardFails)throw Error('denied');copyStatus.copied=value;}}},
    FormData:class {constructor(value){this.form=value;}},
    DOMParser:class {parseFromString(){return {querySelector(){return {textContent:'表单已失效，请刷新页面重试'};}};}},
    fetch:async()=>{if(errorResponse)return {ok:false,async text(){return '<error>';}}; throw Error('网络连接中断');},
  };
  vm.runInNewContext(source,context);
  return {field,result,copyStatus,error,submit,form,async click(selector){
    for(const handler of handlers.click) await handler({target:{closest(value){return value===selector?{}:null;}}});
  },async submitForm(){for(const handler of handlers.submit)await handler({target:form,preventDefault(){}});},
    leave(){handlers.pagehide.forEach(handler=>handler());}};
}

test('copying works and page departure clears all token representations',async()=>{
  const ui=harness();
  await ui.click('[data-token-copy]');
  assert.equal(ui.copyStatus.copied,'one-time-test-token');
  assert.match(ui.copyStatus.textContent,/已复制/);
  ui.leave();
  assert.equal(ui.field.value,'');
  assert.equal(ui.field.defaultValue,'');
  assert.equal(ui.field.textContent,'');
  assert.equal(ui.result.hidden,true);
});
test('clipboard denial selects token and explains manual copy',async()=>{
  const ui=harness({clipboardFails:true});
  await ui.click('[data-token-copy]');
  assert.equal(ui.field.selected,true);
  assert.match(ui.copyStatus.textContent,/Ctrl\+C/);
});
for(const errorResponse of [false,true]) {
  test(`${errorResponse?'expired form':'network failure'} keeps console open and restores submit control`,async()=>{
    const ui=harness({errorResponse});
    await ui.submitForm();
    assert.equal(ui.submit.disabled,false);
    assert.equal(ui.submit.textContent,'保存设置');
    assert.equal(ui.error.hidden,false);
    assert.ok(ui.error.textContent);
    assert.equal(ui.error.focused,true);
    assert.equal(ui.field.value,'one-time-test-token');
  });
}
