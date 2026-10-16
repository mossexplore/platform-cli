const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('approval shortcuts restore defaults, select all, and clear without submitting', () => {
  const changes = [];
  const choices = [true, false, true].map((flag, id) => ({
    checked: false, dataset: { defaultGrant: String(flag) },
    dispatchEvent: (event) => changes.push({ id, type: event.type }),
  }));
  const buttons = ['default', 'all', 'none'].map(mode => ({
    dataset: { environmentSelection: mode },
    addEventListener(type, handler) { assert.equal(type, 'click'); this.click = handler; },
  }));
  const group = { querySelectorAll: selector => selector.startsWith('input') ? choices : buttons };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/approval-environments.js'), 'utf8'), {
    document: { querySelectorAll: () => [group] },
    Event: class { constructor(type) { this.type = type; } },
  });
  buttons[0].click();
  assert.deepEqual(choices.map(c => c.checked), [true, false, true]);
  buttons[1].click();
  assert.ok(choices.every(c => c.checked));
  buttons[2].click();
  assert.ok(choices.every(c => !c.checked));
  choices[1].checked = true;
  buttons[0].click();
  assert.deepEqual(choices.map(c => c.checked), [true, false, true]);
  assert.equal(changes.length, 12);
});
