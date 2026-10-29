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
