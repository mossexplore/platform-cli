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
