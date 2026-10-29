const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('progress reports elapsed time and status polling recovers a lost completion event', async () => {
  const nodes = new Map();
  const $ = id => { if (!nodes.has(id)) nodes.set(id, {textContent:'',scrollHeight:10}); return nodes.get(id); };
  let timer, cleared = 0, busy = true, source, polls = 0;
  class EventSource {
    constructor() { this.handlers = {}; source = this; }
    addEventListener(kind, handler) { this.handlers[kind] = handler; }
    close() { this.closed = true; }
  }
  const output = {};
  const body = {timeline:{finish:(answer)=>{output.content=answer;}},append:()=>{}};
  const context = vm.createContext({
    state:{stream:null,run:'r'}, $, body, EventSource, Date, Map, Number, JSON,
    setInterval:fn=>{timer=fn; return 1;}, clearInterval:()=>cleared++,
    api:async()=>{polls++;return {status:'completed',answer:'最终回答',error:''};},
    markdown:(node,value)=>{node.content=value;}, setBusy:value=>{busy=value;},
    notice:()=>{}, text:()=>({}), icon:()=>({}), window:{dispatchEvent:()=>{}},Event:class {},
  });
  const code=fs.readFileSync(path.join(__dirname,'../app/static/chat.js'),'utf8')
    .replace(/import[\s\S]*?from "\.\/api\.js";/,'').replace(/import .*message-parts.*;/,'').replace(/export /g,'');
  vm.runInContext(code,context);
  vm.runInContext("connectEvents('r', body)",context);
  source.handlers['run.progress']({lastEventId:'1',data:JSON.stringify({stage:'model_waiting',elapsed_seconds:12,model_requests:2})});
  assert.match($('connection-status').textContent,/第 2 次模型请求/);
  assert.match($('connection-status').textContent,/12 秒/);
  for(let i=0;i<5;i++) await timer();
  assert.equal(polls,1);
  assert.equal(busy,false);
  assert.equal(output.content,'最终回答');
  assert.equal($('connection-status').textContent,'查询完成');
  assert.ok(source.closed && cleared);
});
