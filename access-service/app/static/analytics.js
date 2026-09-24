'use strict';
const period = document.querySelector('[data-analytics-period]');
const custom = document.querySelector('[data-analytics-custom]');
if (period && custom) {
  const update = () => { custom.hidden = period.value !== 'custom'; };
  period.addEventListener('change', update);
  update();
}
