const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../app/static/history.js', 'utf8');
const node = () => ({});
const ctx = vm.createContext({ Intl, Date, Number, Boolean, JSON, $: node, document: { addEventListener() {} } });
vm.runInContext(source.replace(/import[^;]+;/, '').replace(/export /g, ''), ctx);
const { historyGroup, filterHistory } = vm.runInContext('({historyGroup, filterHistory})', ctx);
test('history uses Beijing calendar boundaries and handles missing dates', () => {
  const now = Date.parse('2026-10-29T00:30:00+08:00');
  assert.equal(historyGroup({updated_at:'2026-10-28T16:01:00Z'}, {}, now), '今天');
  assert.equal(historyGroup({updated_at:'2026-10-28T15:59:00Z'}, {}, now), '昨天');
  assert.equal(historyGroup({}, {}, now), '更早');
  assert.equal(historyGroup({}, {pinned:true}, now), '置顶');
});
test('search combines keywords and archived conversations can be restored to normal view', () => {
  const items = [{id:'a',title:'训练 Task 分析'}, {id:'b',title:'模型'}];
  const prefs = {a:{archived:true}};
  assert.equal(filterHistory(items, 'TASK 训练', prefs, true).length, 1);
  assert.equal(filterHistory(items, 'TASK', prefs, false).length, 0);
  prefs.a.archived = false;
  assert.equal(filterHistory(items, 'task', prefs, false)[0].id, 'a');
});

test('delete menu confirms physical deletion, resets current chat, and preserves it on failure', async () => {
  function element(tag, content = '') {
    return { tag, textContent:content, children:[], dataset:{}, classList:{add(){}},
      setAttribute(){}, append(...items){this.children.push(...items);} };
  }
  const notices=[], calls=[], nodes=new Map();
  const get=id=>{if(!nodes.has(id))nodes.set(id, {value:'',replaceChildren(){},append(){},setAttribute(){}});return nodes.get(id);};
  let confirmed=false, failure=false, resets=0;
  const state={conversation:{id:'a'}};
  const context=vm.createContext({Intl,Date,Number,Boolean,JSON,state,$:get,text:element,icon:()=>element('i'),
    document:{addEventListener(){},querySelectorAll(){return [];}},
    window:{confirm:()=>confirmed}, localStorage:{setItem(){}},notice:m=>notices.push(m),
    api:async(...args)=>{calls.push(args);if(failure)throw new Error('删除失败');},
    reset:async()=>{resets++;state.conversation=null;}});
  vm.runInContext(source.replace(/import[^;]+;/,'').replace(/export /g,''),context);
  vm.runInContext('onDeleted=reset; rows=[{id:"a",title:"测试"}]; prefs={a:{pinned:true}};',context);
  const row=vm.runInContext('entry(rows[0])',context);
  const button=row.children[2].children.find(b=>b.textContent==='删除');
  assert.ok(button);
  await button.onclick();
  assert.equal(calls.length,0);
  confirmed=true; failure=true;
  await button.onclick();
  assert.equal(vm.runInContext('rows.length',context),1);
  assert.equal(resets,0);
  assert.equal(notices.at(-1),'删除失败');
  failure=false;
  await button.onclick();
  assert.equal(calls.at(-1)[0],'/conversations/a');
  assert.equal(calls.at(-1)[1].method,'DELETE');
  assert.equal(vm.runInContext('rows.length',context),0);
  assert.equal(vm.runInContext('prefs.a',context),undefined);
  assert.equal(resets,1);
});
