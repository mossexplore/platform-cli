const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');

function filterAt(now) {
  const clicks = [];
  const inputs = Object.fromEntries(['begin', 'end'].map(name => [name, {
    value: '', addEventListener(type, handler) { this[type] = handler; },
    closest() { return range; },
  }]));
  const chips = ['1h', '24h', '7d', '30d'].map(preset => ({
    dataset: {preset}, active: false,
    closest() { return range; },
    classList: {
      toggle(name, active) { chips.find(chip => chip.dataset.preset === preset).active = active; },
      remove() { chips.find(chip => chip.dataset.preset === preset).active = false; },
    },
  }));
  const range = {
    querySelector(selector) { return inputs[selector.includes('begin') ? 'begin' : 'end']; },
    querySelectorAll() { return chips; },
  };
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [now])); }
  }
  vm.runInNewContext(source, {
    Date: Clock,
    document: {
      addEventListener(type, handler) { if (type === 'click') clicks.push(handler); },
      querySelectorAll(selector) { return selector === '[data-time-range] input' ? Object.values(inputs) : []; },
    },
  });
  return {inputs, chips, async click(chip) {
    const target = {closest(selector) { return selector === '[data-preset]' ? chip : null; }};
    for (const handler of clicks) await handler({target});
  }};
}

for (const timezone of ['Asia/Shanghai', 'UTC', 'America/Los_Angeles']) {
  test(`presets use Beijing time in ${timezone}, including calendar and DST boundaries`, async () => {
    const previous = process.env.TZ;
    process.env.TZ = timezone;
    try {
      for (const [now, expectedEnd] of [
        ['2026-09-09T12:00:00Z', '2026-09-09T20:00:00'],
        ['2026-12-31T20:00:00Z', '2027-01-01T04:00:00'],
        ['2024-02-29T20:00:00Z', '2024-03-01T04:00:00'],
        ['2026-03-08T10:30:00Z', '2026-03-08T18:30:00'],
        ['2026-11-01T09:30:00Z', '2026-11-01T17:30:00'],
      ]) {
        const filter = filterAt(now);
        for (const [index, hours] of [1, 24, 168, 720].entries()) {
          await filter.click(filter.chips[index]);
          assert.equal(filter.inputs.end.value, expectedEnd);
          // Match the backend's interpretation of timezone-less values as UTC+8.
          assert.equal(Date.parse(filter.inputs.begin.value + '+08:00'), Date.parse(now) - hours * 3600000);
          assert.equal(filter.chips.filter(chip => chip.active).length, 1);
          assert.equal(filter.chips[index].active, true);
          filter.inputs.begin.input();
          assert.equal(filter.chips.some(chip => chip.active), false);
        }
      }
    } finally {
      if (previous === undefined) delete process.env.TZ;
      else process.env.TZ = previous;
    }
  });
}
