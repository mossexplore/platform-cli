'use strict';
// Integer event counts need integer, non-duplicated axis labels, even for 0–3 events.
function countScale(maximum) {
  const target = Math.max(1, maximum) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(target));
  const step = Math.max(1, [1, 2, 5, 10].map(value => value * magnitude).find(value => value >= target));
  const top = Math.max(step, Math.ceil(maximum / step) * step);
  const ticks = Array.from({length: Math.round(top / step) + 1}, (_, index) => index * step);
  return {maximum: top, ticks};
}
if (typeof module !== 'undefined') module.exports = {countScale};
