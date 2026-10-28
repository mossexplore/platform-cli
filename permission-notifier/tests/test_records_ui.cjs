const {test}=require('node:test');
const assert=require('node:assert/strict');
const {recentRange}=require('../src/permission_notifier/static/records.js');
test('recent three days is a rolling 72 hours expressed in Beijing time',()=>{
  const result=recentRange(Date.parse('2026-10-28T02:30:45Z'));
  assert.deepEqual(result,{start:'2026-10-25T10:30:45',end:'2026-10-28T10:30:45',source:''});
});
test('range is independent of machine timezone and handles date boundaries',()=>{
  const result=recentRange(Date.parse('2026-01-01T00:00:00Z'));
  assert.equal(result.start,'2025-12-29T08:00:00');
  assert.equal(result.end,'2026-01-01T08:00:00');
});
test('each records entry refreshes end time to the second and keeps other filters',()=>{
  const vm=require('node:vm');
  const fs=require('node:fs');
  const endInput={value:''};
  const context=vm.createContext({$:id=>{assert.equal(id,'record-end');return endInput;}});
  vm.runInContext(fs.readFileSync(require.resolve('../src/permission_notifier/static/records.js'),'utf8'),context);
  vm.runInContext("recordFilters={start:'2026-10-20T08:00:00',end:'2026-10-27T08:00:00',source:'permission'};recordsPage=3;refreshRecords=()=>JSON.stringify({filters:recordFilters,page:recordsPage});",context);
  let result=JSON.parse(vm.runInContext("enterRecords(Date.parse('2026-10-28T02:30:45.999Z'))",context));
  assert.deepEqual(result,{filters:{start:'2026-10-20T08:00:00',end:'2026-10-28T10:30:45',source:'permission'},page:1});
  assert.equal(endInput.value,result.filters.end);
  result=JSON.parse(vm.runInContext("enterRecords(Date.parse('2026-10-28T02:30:49Z'))",context));
  assert.equal(result.filters.end,'2026-10-28T10:30:49');
  assert.equal(endInput.value,result.filters.end);
});
