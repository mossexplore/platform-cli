'use strict';
// Self-contained charts keep the offline management console independent of CDNs.
const host = document.querySelector('[data-analysis-chart]');
if (host) {
  const data = JSON.parse(host.dataset.analysisChart);
  const graphic = host.querySelector('.analytics-plot-graphic');
  const legend = host.querySelector('.analytics-plot-legend');
  const scrollHint = host.querySelector('.analytics-scroll-hint');
  const description = document.querySelector('[data-analysis-description]');
  const buttons = [...document.querySelectorAll('[data-analysis-view]')];
  const colors = ['#0052d9', '#00a870', '#7b61c9', '#ed7b2f', '#df658b', '#a9aeb8'];
  const ns = 'http://www.w3.org/2000/svg';
  const labels = {
    commands: `按${data.grain}查看各命令的调用分布`,
    trend: `按${data.grain}查看授权检查、通过与拒绝的变化`,
    distribution: '所选时段内各命令的调用次数占比',
    ranking: '所选时段内调用次数最多的命令',
  };
  let active = 'commands';

  function svgNode(tag, attributes = {}, content) {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function add(parent, tag, attributes, content) {
    const node = svgNode(tag, attributes, content);
    parent.appendChild(node);
    return node;
  }

  function linked(parent, href, title, drawing) {
    const target = href ? add(parent, 'a', {href}) : add(parent, 'g', {});
    add(target, 'title', {}, title);
    drawing(target);
  }

  function canvas(width, height) {
    const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, width, height,
      'aria-hidden': 'true', class: 'analysis-svg'});
    graphic.replaceChildren(svg);
    return svg;
  }

  function legendItems(items) {
    legend.replaceChildren();
    items.forEach((item, index) => {
      const entry = document.createElement('span');
      const swatch = document.createElement('i');
      swatch.className = `analysis-swatch analysis-swatch-${index % colors.length}`;
      entry.append(swatch, document.createTextNode(item));
      legend.appendChild(entry);
    });
  }

  function axes(svg, width, height, left, bottom, maximum, points) {
    const top = 24;
    const plotHeight = height - top - bottom;
    for (let i = 0; i <= 4; i++) {
      const y = top + plotHeight * i / 4;
      add(svg, 'line', {x1: left, y1: y, x2: width - 20, y2: y, class: 'analysis-grid-line'});
      add(svg, 'text', {x: left - 10, y: y + 4, 'text-anchor': 'end', class: 'analysis-axis-label'},
        String(Math.round(maximum * (4 - i) / 4)));
    }
    const visible = Math.max(1, Math.floor((width - left - 20) / 84));
    const every = Math.max(1, Math.ceil(points.length / visible));
    points.forEach((point, index) => {
      if (index % every && index !== points.length - 1) return;
      const x = left + (index + 0.5) * (width - left - 20) / points.length;
      add(svg, 'text', {x, y: height - 13, 'text-anchor': 'middle', class: 'analysis-axis-label'}, point.label);
    });
    return {top, plotHeight, plotWidth: width - left - 20};
  }

  function timeSize() {
    const width = Math.max(560, graphic.clientWidth, Math.min(2500, data.points.length * 38 + 100));
    return {width, height: 340, left: 50, bottom: 42};
  }

  function commandBars() {
    const {width, height, left, bottom} = timeSize();
    const svg = canvas(width, height);
    const maximum = Math.max(1, ...data.points.map(point => point.total));
    const {top, plotHeight, plotWidth} = axes(svg, width, height, left, bottom, maximum, data.points);
    const slot = plotWidth / data.points.length;
    const barWidth = Math.min(54, slot * 0.7);
    data.points.forEach((point, index) => {
      let accumulated = 0;
      [...point.commands, point.other].forEach((value, colorIndex) => {
        if (!value) return;
        const barHeight = value / maximum * plotHeight;
        const y = top + plotHeight - accumulated - barHeight;
        const name = colorIndex === data.commands.length ? '其他命令' : data.commands[colorIndex];
        const href = colorIndex === data.commands.length ? '' :
          `${point.href}&command_exact=${encodeURIComponent(name)}`;
        linked(svg, href, `${point.label} · ${name}：${value} 次`, target => {
          add(target, 'rect', {x: left + slot * index + (slot - barWidth) / 2, y,
            width: barWidth, height: barHeight, fill: colors[colorIndex], class: 'analysis-mark'});
        });
        accumulated += barHeight;
      });
    });
    legendItems([...data.commands, ...(data.points.some(point => point.other) ? ['其他命令'] : [])]);
  }

  function trendLines() {
    const {width, height, left, bottom} = timeSize();
    const svg = canvas(width, height);
    const maximum = Math.max(1, ...data.points.map(point => point.total));
    const {top, plotHeight, plotWidth} = axes(svg, width, height, left, bottom, maximum, data.points);
    [['total', '检查次数', colors[0]], ['allowed', '通过', colors[1]],
      ['denied', '拒绝', '#d54941']].forEach(([key, label, color]) => {
      const coordinates = data.points.map((point, index) => [
        left + (index + 0.5) * plotWidth / data.points.length,
        top + plotHeight - point[key] / maximum * plotHeight]);
      add(svg, 'polyline', {points: coordinates.map(pair => pair.join(',')).join(' '),
        fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round'});
      coordinates.forEach(([x, y], index) => linked(svg, data.points[index].href,
        `${data.points[index].label} · ${label}：${data.points[index][key]} 次`, target => {
          add(target, 'circle', {cx: x, cy: y, r: 5, fill: color, class: 'analysis-mark'});
        }));
    });
    legendItems(['检查次数', '通过', '拒绝']);
    legend.lastElementChild?.classList.add('analysis-legend-danger');
  }

  function distributionPie() {
    const width = Math.max(340, graphic.clientWidth);
    const height = 340;
    const svg = canvas(width, height);
    const total = data.distribution.reduce((sum, item) => sum + item.value, 0);
    const radius = 110;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    data.distribution.forEach((item, index) => {
      const length = item.value / total * circumference;
      linked(svg, item.href, `${item.label}：${item.value} 次（${(item.value / total * 100).toFixed(1)}%）`, target => {
        add(target, 'circle', {cx: width / 2, cy: 158, r: radius, fill: 'none',
          stroke: colors[index], 'stroke-width': 46,
          'stroke-dasharray': `${Math.max(0, length - 2)} ${circumference}`,
          'stroke-dashoffset': -offset, transform: `rotate(-90 ${width / 2} 158)`,
          class: 'analysis-mark'});
      });
      offset += length;
    });
    add(svg, 'text', {x: width / 2, y: 152, 'text-anchor': 'middle', class: 'analysis-pie-total'}, String(total));
    add(svg, 'text', {x: width / 2, y: 176, 'text-anchor': 'middle', class: 'analysis-axis-label'}, '次授权检查');
    legendItems(data.distribution.map(item => `${item.label} ${item.value} 次 · ${(item.value / total * 100).toFixed(1)}%`));
  }

  function rankingBars() {
    const width = Math.max(560, graphic.clientWidth);
    const height = Math.max(300, data.ranking.length * 42 + 64);
    const left = 210;
    const svg = canvas(width, height);
    const maximum = Math.max(1, ...data.ranking.map(item => item.value));
    const barArea = width - left - 95;
    data.ranking.forEach((item, index) => {
      const y = 38 + index * 42;
      add(svg, 'line', {x1: left, y1: y + 24, x2: width - 20, y2: y + 24, class: 'analysis-grid-line'});
      linked(svg, item.href, `${item.label}：${item.value} 次`, target => {
        add(target, 'text', {x: left - 12, y: y + 16, 'text-anchor': 'end', class: 'analysis-rank-label'},
          item.label.length > 23 ? `${item.label.slice(0, 22)}…` : item.label);
        add(target, 'rect', {x: left, y, width: barArea * item.value / maximum,
          height: 24, rx: 4, fill: colors[0], class: 'analysis-mark'});
      });
      add(svg, 'text', {x: left + barArea * item.value / maximum + 10, y: y + 17,
        class: 'analysis-rank-value'}, String(item.value));
    });
    legendItems(['按命令汇总的授权检查次数']);
  }

  function render(view) {
    active = view;
    buttons.forEach(button => {
      const selected = button.dataset.analysisView === view;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    description.textContent = labels[view];
    graphic.setAttribute('aria-label', `${buttons.find(button => button.dataset.analysisView === view).textContent}：${labels[view]}`);
    ({commands: commandBars, trend: trendLines, distribution: distributionPie, ranking: rankingBars})[view]();
    scrollHint.hidden = graphic.querySelector('svg').width.baseVal.value <= graphic.clientWidth;
  }

  buttons.forEach(button => button.addEventListener('click', () => render(button.dataset.analysisView)));
  new ResizeObserver(() => render(active)).observe(graphic);
  render(active);
}
