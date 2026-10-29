const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function setup() {
  function node(tag,content='',cls='') { return {tag,content,className:cls,children:[],classList:{add(){}},append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=[...nodes];},get firstChild(){return this.children[0];},get lastChild(){return this.children.at(-1);}}; }
  const body=node('body');
  const context=vm.createContext({Map,body,text:node,icon:()=>node('i'),markdown:(el,content)=>{el.content=content;}});
  const code=fs.readFileSync(path.join(__dirname,'../app/static/message-parts.js'),'utf8').replace(/import[^;]+;/,'').replace(/export /g,'');
  vm.runInContext(code,context);
  const timeline=vm.runInContext('createTimeline(body,{list_models:"查询模型列表"})',context);
  return {timeline,children:()=>body.children[0].children};
}
test('text/tool/text are distinct DOM siblings and completion never erases introduction',()=>{
  const {timeline,children}=setup();
  timeline.delta('先查询');timeline.delta('模型。');
  timeline.startTool({tool_call_id:'one',name:'list_models'});
  timeline.completeTool({tool_call_id:'one',status:'completed'});
  timeline.delta('最终');timeline.delta('结果。');
  assert.deepEqual(children().map(n=>n.className),['markdown','tool-step','markdown']);
  assert.deepEqual(children().filter(n=>n.className==='markdown').map(n=>n.content),['先查询模型。','最终结果。']);
  timeline.finish('最终结果。');
  assert.equal(children()[0].content,'先查询模型。');
  assert.equal(children()[1].lastChild.textContent,'已完成');
  assert.equal(children()[2].content,'最终结果。');
});
test('persisted blocks and interrupted/replayed completion keep exact ordering',()=>{
  const {timeline,children}=setup();
  const parts=[{type:'text',content:'之前'},{type:'tool',id:'one',name:'list_models',status:'cancelled'},{type:'text',content:'之后'}];
  timeline.finish('之后',parts);timeline.finish('之后',parts);
  assert.equal(children().length,3);
  assert.equal(children()[0].content,'之前');
  assert.equal(children()[1].lastChild.textContent,'已停止');
  assert.equal(children()[2].content,'之后');
});
