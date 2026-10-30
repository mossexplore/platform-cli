const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function node(tag, content='', cls='') {
  return {tag,textContent:content,className:cls,dataset:{},children:[],disabled:false,
    append(...children){this.children.push(...children);},
    querySelectorAll(selector){ return this.children.filter(n => selector==='button' ? n.tag==='button' : n.className==='action-confirmation'); }};
}
test('confirmation renders untrusted parameters as text and only clicks approve exact action', async () => {
  const calls=[], body=node('div');
  const context=vm.createContext({state:{session:{environment_id:'dev'}},text:node,
    post:async(...args)=>calls.push(args), JSON, body});
  const code=fs.readFileSync(path.join(__dirname,'../app/static/actions.js'),'utf8')
    .replace(/import[\s\S]*?from [^;]+;/g,'').replace(/export /g,'');
  vm.runInContext(code,context);
  context.data={action_id:'a', name:'delete_train_task',business:{businessId:'b'},arguments:{task_id:'<script>x</script>'},details:null};
  vm.runInContext("showAction(body,'run',data)",context);
  assert.equal(calls.length,0);
  const card=body.children[0];
  assert.match(card.children[2].textContent, /<script>x<\/script>/);
  assert.equal(card.children[2].innerHTML,undefined);
  await card.children[3].onclick();
  assert.equal(calls[0][0],'/runs/run/actions/a');
  assert.equal(JSON.stringify(calls[0][1]),'{"approved":true}');
  assert.equal(card.children[3].disabled,true);
  assert.equal(card.children[4].disabled,true);
  vm.runInContext("settleAction(body,{action_id:'a',approved:true})",context);
  assert.equal(calls.length,1);
});
