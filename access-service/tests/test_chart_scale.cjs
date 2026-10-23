const test = require('node:test');
const assert = require('node:assert/strict');
const {countScale} = require('../app/static/chart-scale.js');

for (const maximum of [0,1,2,3,4,5,6,7,11,99,1001,1000000]) {
  test(`count axis is unique and integral for ${maximum} events`, () => {
    const scale = countScale(maximum);
    assert.equal(scale.ticks[0], 0);
    assert.equal(scale.ticks.at(-1), scale.maximum);
    assert.ok(scale.maximum >= maximum);
    assert.ok(scale.ticks.length <= 6);
    assert.equal(new Set(scale.ticks).size, scale.ticks.length);
    scale.ticks.forEach((value,i) => {
      assert.ok(Number.isInteger(value));
      if (i) assert.ok(value > scale.ticks[i-1]);
    });
    assert.equal(countScale(scale.maximum).maximum, scale.maximum);
  });
}
