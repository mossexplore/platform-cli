const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('manual command input normalizes lines and counts unique additions and removals', () => {
  const handlers = {};
  const input = {value: 'ml jupyter files upload', addEventListener: (name, fn) => handlers[name] = fn};
  const count = {};
  const panel = {querySelector: selector => selector.includes('input') ? input : count};
  const source = fs.readFileSync(path.join(__dirname, '../app/static/command-policy.js'), 'utf8');
  vm.runInNewContext(source, {document: {querySelectorAll: () => [panel]}});
  input.value = '\n ml  jupyter files upload \r\nml train start\nml train start\n';
  handlers.input();
  assert.match(count.textContent, /已禁止 2 个命令/);
  assert.match(count.textContent, /新增禁止 1 个/);
  input.value = '';
  handlers.input();
  assert.match(count.textContent, /已禁止 0 个命令/);
  assert.match(count.textContent, /解除禁止 1 个/);
});
