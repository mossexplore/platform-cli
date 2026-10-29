const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function helpers(){
  const context=vm.createContext({JSON,Boolean,text:(tag,content)=>({tag,textContent:content}),businessName:b=>b.team_name?b.tenant_name+' / '+b.team_name:b.tenant_name});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/business-picker.js'),'utf8').replace(/import[^;]+;/,'').replace(/export /g,''),context);
  return vm.runInContext('({selectionKey,filterBusinesses,bindBusinessPicker})',context);
}
const tenant={type:'tenant',department_id:'d',department_name:'数据平台',tenant_id:'BI',tenant_name:'数据分析',businessId:'same',team_id:'',team_name:''};
const team={...tenant,type:'team',team_id:'TEAM2',team_name:'推荐团队'};
test('tenant search supports names, IDs, case folding and multiple words',()=>{
  const {filterBusinesses,selectionKey}=helpers();
  assert.equal(filterBusinesses([tenant,team],'推荐').length,1);
  assert.equal(filterBusinesses([tenant,team],'数据平台 team2')[0].team_id,'TEAM2');
  assert.equal(filterBusinesses([tenant,team],'bi').length,2);
  assert.equal(filterBusinesses([tenant,team],'missing').length,0);
  assert.notEqual(selectionKey(tenant),selectionKey(team));
});
test('picker retains the exact previous team and disables submit for empty search results',()=>{
  const {bindBusinessPicker,selectionKey}=helpers();
  const select={value:'',children:[],replaceChildren(){this.children=[];this.value='';},append(option){this.children.push(option);if(option.selected)this.value=option.value;}};
  const elements={search:{value:''},select,count:{},empty:{},confirm:{}};
  bindBusinessPicker([tenant,team],team,elements);
  assert.equal(select.value,selectionKey(team));
  elements.search.value='没有';elements.search.oninput();
  assert.equal(select.children.length,0);
  assert.equal(elements.confirm.disabled,true);
  assert.equal(select.disabled,true);
  assert.equal(elements.empty.hidden,false);
  elements.search.value='推荐';elements.search.oninput();
  assert.equal(select.value,selectionKey(team));
  assert.equal(elements.confirm.disabled,false);
});
