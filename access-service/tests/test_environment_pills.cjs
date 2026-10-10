const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../app/static/environment-pills.js'), 'utf8');
function setup(widths, width) {
  const pills = widths.map(width => ({hidden: false, getBoundingClientRect: () => ({width})}));
  const button = {hidden: true, textContent: '', setAttribute(k, v) { this[k] = v; },
    addEventListener(k, fn) { this[k] = fn; }, getBoundingClientRect: () => ({width: 100})};
  const list = {clientWidth: width, classList: {add() {}, remove() {}},
    querySelectorAll: () => pills, querySelector: () => button};
  let resize;
  vm.runInNewContext(source, {document: {querySelectorAll: () => [list]},
    getComputedStyle: () => ({columnGap: '6'}), ResizeObserver: class {
      constructor(fn) { resize = fn; } observe() {}
    }});
  return {pills, button, list, resize, visible: () => pills.filter(p => !p.hidden).length};
}
test('all labels fit without reserving unnecessary button space', () => {
  const view = setup([50, 50, 50], 162);
  assert.equal(view.visible(), 3);
  assert.equal(view.button.hidden, true);
});
test('fills available width, reserves disclosure space and responds to resize', () => {
  const view = setup(Array(10).fill(25), 256);
  assert.equal(view.visible(), 5);
  assert.equal(view.button.textContent, '展开全部（10）');
  view.button.click();
  assert.equal(view.visible(), 10);
  assert.equal(view.button['aria-expanded'], 'true');
  view.list.clientWidth = 150;
  view.resize();
  assert.equal(view.visible(), 10);
  view.button.click();
  assert.equal(view.visible(), 1);
  view.list.clientWidth = 500;
  view.resize();
  assert.equal(view.visible(), 10);
  assert.equal(view.button.hidden, true);
});
test('oversized first label falls back to view all and remains accessible', () => {
  const view = setup([600, 30], 256);
  assert.equal(view.visible(), 0);
  assert.equal(view.button.textContent, '查看全部（2）');
  view.button.click();
  assert.equal(view.visible(), 2);
  assert.equal(view.button.textContent, '收起');
});
