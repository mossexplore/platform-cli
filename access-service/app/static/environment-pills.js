'use strict';

// Measure natural label widths, including gaps and the disclosure control.
document.querySelectorAll('[data-environment-pills]').forEach((list) => {
  const pills = [...list.querySelectorAll('.badge')];
  const button = list.querySelector('.environment-toggle');
  if (!button) return;
  let expanded = false;
  const render = () => {
    list.classList.add('is-collapsed');
    pills.forEach((pill) => { pill.hidden = false; });
    button.hidden = false;
    button.textContent = `展开全部（${pills.length}）`;
    const gap = parseFloat(getComputedStyle(list).columnGap) || 0;
    const widths = pills.map((pill) => pill.getBoundingClientRect().width);
    const available = list.clientWidth;
    const total = widths.reduce((sum, width) => sum + width, 0) + gap * (pills.length - 1);
    let count = pills.length;
    if (total > available) {
      let used = button.getBoundingClientRect().width;
      count = 0;
      for (const width of widths) {
        if (used + gap + width > available) break;
        used += gap + width;
        count++;
      }
    }
    if (expanded) {
      list.classList.remove('is-collapsed');
      button.textContent = '收起';
    } else {
      pills.forEach((pill, index) => { pill.hidden = index >= count; });
      if (!count) button.textContent = `查看全部（${pills.length}）`;
    }
    button.hidden = !expanded && count === pills.length;
    button.setAttribute('aria-expanded', String(expanded));
  };
  button.addEventListener('click', () => {
    expanded = !expanded;
    render();
  });
  // Ignore height-only changes caused by expansion to avoid observer loops.
  let lastWidth;
  new ResizeObserver(() => {
    if (lastWidth === list.clientWidth) return;
    lastWidth = list.clientWidth;
    render();
  }).observe(list);
  document.fonts?.ready.then(render);
  render();
});
