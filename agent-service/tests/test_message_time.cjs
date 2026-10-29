const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const ctx = vm.createContext({Intl, Date, Number, Object, text: () => ({removeAttribute(){ delete this.dateTime; }})});
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/message-time.js','utf8').replace(/import[^;]+;/,'').replace(/export /g,''),ctx);
const {formatMessageTime,attachMessageTime} = vm.runInContext('({formatMessageTime,attachMessageTime})',ctx);
test('timestamps convert UTC and offsets to Beijing time including midnight',()=>{
  assert.equal(formatMessageTime('2026-09-08T06:54:36.000+00:00'),'2026-09-08 14:54:36');
  assert.equal(formatMessageTime('2026-10-28T16:00:00Z'),'2026-10-29 00:00:00');
  assert.equal(formatMessageTime('2026-10-29T08:05:09+08:00'),'2026-10-29 08:05:09');
  assert.equal(formatMessageTime(null),''); assert.equal(formatMessageTime('bad'),'');
});
test('message timestamp stays below content, hidden until a persisted time is available',()=>{
  const row={children:[{content:'answer'}],append(node){this.children.push(node);}};
  const update=attachMessageTime(row,null), time=row.children[1];
  assert.equal(time.hidden,true);
  update('2026-09-08T06:54:36Z');
  assert.equal(time.textContent,'2026-09-08 14:54:36');
  assert.equal(time.dateTime,'2026-09-08T06:54:36Z');
  assert.equal(time.hidden,false); assert.equal(row.children.length,2);
  update('bad'); assert.equal(time.hidden,true);
});
