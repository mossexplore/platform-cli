'use strict';
const filterToggle = document.querySelector('[data-toggle-analytics-filters]');
if (filterToggle) {
  filterToggle.addEventListener('click', () => {
    const fields = document.getElementById(filterToggle.getAttribute('aria-controls'));
    fields.hidden = !fields.hidden;
    filterToggle.setAttribute('aria-expanded', String(!fields.hidden));
    filterToggle.textContent = fields.hidden ? '更多筛选' : '收起筛选';
  });
}
// Self-contained charts keep the offline management console independent of CDNs.
const host = document.querySelector('[data-analysis-chart]');
if (host) {
  const data = JSON.parse(host.dataset.analysisChart);
  const graphic = host.querySelector('.analytics-plot-graphic');
  const legend = host.querySelector('.analytics-plot-legend');
  const scrollHint = host.querySelector('.analytics-scroll-hint');
  const controlsBar = host.querySelector('[data-analysis-controls]');
  const topWrap = host.querySelector('[data-analysis-top-wrap]');
  const envWrap = host.querySelector('[data-analysis-env-wrap]');
  const topSelect = host.querySelector('[data-analysis-top]');
  const envSelect = host.querySelector('[data-analysis-env]');
  const errorBox = host.querySelector('[data-analysis-error]');
  const description = document.querySelector('[data-analysis-description]');
  const buttons = [...document.querySelectorAll('[data-analysis-view]')];
  const colors = ['#0052d9', '#00a870', '#7b61c9', '#ed7b2f', '#df658b', '#a9aeb8'];
  const palette = ['#0052d9', '#00a870', '#7b61c9', '#ed7b2f', '#df658b',
    '#029cd4', '#e3a008', '#4f6ef7', '#2ba471', '#d54941', '#8b5cf6', '#6b7280'];
  const ns = 'http://www.w3.org/2000/svg';
  const labels = {
    commands: `按${data.grain}查看各命令的调用分布`,
    trend: `按${data.grain}查看授权检查、通过与拒绝的变化`,
    distribution: '所选时段内各命令的调用次数占比',
    ranking: '所选时段内调用次数最多的命令',
    versions: '所选时段内各 CLI 版本的调用次数占比',
    environments: '所选时段内各环境的调用次数',
  };
  const lockedEnv = data.locked_environment || '';
  const viewControls = {
    distribution: {top: true, env: true},
    ranking: {top: true, env: true},
    versions: {top: false, env: true},
  };
  const appliedFilters = {
    distribution: {top: '10', env: lockedEnv},
    ranking: {top: '10', env: lockedEnv},
    versions: {top: 'all', env: lockedEnv},
  };
  const cache = new Map([
    [`distribution|10|${lockedEnv}`, data.distribution || []],
    [`ranking|10|${lockedEnv}`, data.ranking || []],
    [`versions|all|${lockedEnv}`, data.versions || []],
  ]);
  let active = 'commands';
  let activeController = null;

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
    legend.hidden = !items.length;
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
    const scale = countScale(maximum);
    for (const value of [...scale.ticks].reverse()) {
      const y = top + plotHeight * (1 - value / scale.maximum);
      add(svg, 'line', {x1: left, y1: y, x2: width - 20, y2: y, class: 'analysis-grid-line'});
      add(svg, 'text', {x: left - 10, y: y + 4, 'text-anchor': 'end', class: 'analysis-axis-label'},
        String(value));
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
    const maximum = countScale(Math.max(1, ...data.points.map(point => point.total))).maximum;
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
    const maximum = countScale(Math.max(1, ...data.points.map(point => point.total))).maximum;
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

  function renderEmpty(message) {
    const box = document.createElement('div');
    box.className = 'empty analytics-plot-empty';
    const strong = document.createElement('strong');
    strong.textContent = message;
    const hint = document.createElement('p');
    hint.textContent = '可切换其他环境或调整顶部查询条件。';
    box.append(strong, hint);
    graphic.replaceChildren(box);
    legendItems([]);
  }

  function placeSideLabels(entries, minY, maxY, minGap) {
    const sorted = [...entries].sort((a, b) => a.idealY - b.idealY);
    sorted.forEach((entry, index) => {
      entry.y = Math.max(minY, Math.min(maxY, entry.idealY));
      if (index > 0 && entry.y < sorted[index - 1].y + minGap) {
        entry.y = sorted[index - 1].y + minGap;
      }
    });
    if (sorted.length && sorted[sorted.length - 1].y > maxY) {
      sorted[sorted.length - 1].y = maxY;
      for (let index = sorted.length - 2; index >= 0; index -= 1) {
        if (sorted[index].y > sorted[index + 1].y - minGap) {
          sorted[index].y = sorted[index + 1].y - minGap;
        }
      }
    }
    return sorted;
  }

  function calloutPie(items, {emptyMessage, otherLabel = null}) {
    const total = items.reduce((sum, item) => sum + item.value, 0);
    if (!total) {
      renderEmpty(emptyMessage);
      return;
    }
    const radius = 104;
    const strokeWidth = 42;
    const rOuter = radius + strokeWidth / 2;
    const rElbow = rOuter + 14;
    const labelOffset = rOuter + 34;
    const circumference = 2 * Math.PI * radius;
    const minGap = 22;

    let accumulated = 0;
    const slices = items.map((item, index) => {
      const fraction = item.value / total;
      const startAngle = accumulated * 2 * Math.PI - Math.PI / 2;
      const sweep = fraction * 2 * Math.PI;
      const midAngle = items.length === 1 ? 0 : startAngle + sweep / 2;
      const color = otherLabel && item.label === otherLabel ? '#a9aeb8' : palette[index % palette.length];
      const slice = {
        item,
        color,
        offset: accumulated * circumference,
        length: fraction * circumference,
        pct: (fraction * 100).toFixed(1),
        midAngle,
        isRight: Math.cos(midAngle) >= 0,
      };
      accumulated += fraction;
      return slice;
    });

    const rightSlices = slices.filter(slice => slice.isRight);
    const leftSlices = slices.filter(slice => !slice.isRight);
    const height = Math.max(340, Math.max(rightSlices.length, leftSlices.length) * minGap + 44);
    const width = Math.max(640, graphic.clientWidth);
    const cx = width / 2;
    const cy = height / 2;
    const svg = canvas(width, height);

    slices.forEach(slice => {
      slice.idealY = cy + rElbow * Math.sin(slice.midAngle);
    });
    placeSideLabels(rightSlices, minGap, height - minGap, minGap);
    placeSideLabels(leftSlices, minGap, height - minGap, minGap);

    slices.forEach(slice => {
      const {item, color, offset, length, pct, midAngle, isRight, y} = slice;
      const dash = items.length === 1 ? `${circumference} 0` : `${Math.max(1, length - 2)} ${circumference}`;
      const x1 = cx + rOuter * Math.cos(midAngle);
      const y1 = cy + rOuter * Math.sin(midAngle);
      const x2 = cx + rElbow * Math.cos(midAngle);
      const x3 = cx + (isRight ? labelOffset : -labelOffset);
      const textX = x3 + (isRight ? 6 : -6);
      const maxLabelWidth = Math.max(80, (isRight ? width - textX : textX) - 12);
      const suffix = ` (${pct}%)`;

      linked(svg, item.href, `${item.label}：${item.value} 次（${pct}%）`, target => {
        add(target, 'circle', {cx, cy, r: radius, fill: 'none', stroke: color, 'stroke-width': strokeWidth,
          'stroke-dasharray': dash, 'stroke-dashoffset': -offset,
          transform: `rotate(-90 ${cx} ${cy})`, class: 'analysis-mark'});
        add(target, 'polyline', {
          points: `${x1.toFixed(1)},${y1.toFixed(1)} ${x2.toFixed(1)},${y.toFixed(1)} ${x3.toFixed(1)},${y.toFixed(1)}`,
          stroke: color, class: 'analysis-pie-leader analysis-mark'});
        const text = add(target, 'text', {x: textX, y: y + 4,
          'text-anchor': isRight ? 'start' : 'end', class: 'analysis-pie-label analysis-mark'},
          `${item.label}${suffix}`);
        let name = String(item.label);
        while (text.getComputedTextLength() > maxLabelWidth && name.length > 1) {
          name = name.slice(0, -1);
          text.textContent = `${name}…${suffix}`;
        }
      });
    });

    add(svg, 'text', {x: cx, y: cy - 6, 'text-anchor': 'middle', class: 'analysis-pie-total'}, String(total));
    add(svg, 'text', {x: cx, y: cy + 18, 'text-anchor': 'middle', class: 'analysis-axis-label'}, '次授权检查');
    legendItems([]);
  }

  function categoryBars(items, xAxisLabel, legendLabel, emptyMessage = '所选条件下暂无调用记录') {
    if (!items.length) {
      renderEmpty(emptyMessage);
      return;
    }
    const width = Math.max(560, graphic.clientWidth, items.length * 130 + 70);
    const height = 390;
    const left = 50;
    const bottom = 96;
    const svg = canvas(width, height);
    const maximum = countScale(Math.max(1, ...items.map(item => item.value))).maximum;
    const {top, plotHeight, plotWidth} = axes(svg, width, height, left, bottom, maximum, []);
    const slot = plotWidth / items.length;
    const barWidth = Math.min(64, slot * 0.62);
    add(svg, 'text', {x: 10, y: 16, class: 'analysis-axis-label'}, '次数');
    items.forEach((item, index) => {
      const x = left + slot * (index + 0.5);
      const barHeight = item.value / maximum * plotHeight;
      const y = top + plotHeight - barHeight;
      const label = String(item.label);
      let split = label.lastIndexOf(' ', 16);
      if (split < 7) split = 16;
      const lines = label.length <= 16 ? [label] : [label.slice(0, split), label.slice(split).trimStart()];
      if (lines[1]?.length > 16) lines[1] = `${lines[1].slice(0, 15)}…`;
      linked(svg, item.href, `${item.label}：${item.value} 次`, target => {
        add(target, 'rect', {x: x - barWidth / 2, y, width: barWidth,
          height: barHeight, rx: 4, fill: colors[0], class: 'analysis-mark'});
        const text = add(target, 'text', {x, y: height - bottom + 22,
          'text-anchor': 'middle', class: 'analysis-rank-label'});
        lines.forEach((line, lineIndex) => {
          const span = add(text, 'tspan', {x, dy: lineIndex ? 16 : 0}, line);
          while (span.getComputedTextLength() > slot - 12 && span.textContent.length > 1) {
            span.textContent = `${span.textContent.replace(/…$/, '').slice(0, -1)}…`;
          }
        });
      });
      add(svg, 'text', {x, y: y - 8, 'text-anchor': 'middle',
        class: 'analysis-rank-value'}, String(item.value));
    });
    add(svg, 'text', {x: left + plotWidth / 2, y: height - 12,
      'text-anchor': 'middle', class: 'analysis-axis-label'}, xAxisLabel);
    legendItems([legendLabel]);
  }

  function cacheKey(view, state) {
    return `${view}|${state.top}|${state.env}`;
  }

  function emptyTextFor(env) {
    return env ? `环境 ${env} 在所选范围内暂无调用记录` : '所选范围内暂无调用记录';
  }

  function drawView(view) {
    const filters = appliedFilters[view];
    const items = filters && cache.get(cacheKey(view, filters));
    if (view === 'commands') commandBars();
    else if (view === 'trend') trendLines();
    else if (view === 'environments') categoryBars(data.environments || [], '环境标识', '按环境汇总的授权检查次数');
    else if (view === 'distribution') {
      calloutPie(items, {emptyMessage: emptyTextFor(filters.env), otherLabel: '其他命令'});
    } else if (view === 'ranking') {
      const env = filters.env;
      const legendLabel = env ? `按命令汇总的授权检查次数（环境：${env}）` : '按命令汇总的授权检查次数';
      categoryBars(items, '命令名称', legendLabel, emptyTextFor(env));
    } else if (view === 'versions') {
      calloutPie(items, {emptyMessage: emptyTextFor(filters.env)});
    }
    const rendered = graphic.querySelector('svg');
    scrollHint.hidden = !rendered || rendered.width.baseVal.value <= graphic.clientWidth;
  }

  function syncControls(view) {
    if (!controlsBar) return;
    const config = viewControls[view];
    controlsBar.hidden = !config;
    if (errorBox) {
      errorBox.textContent = '';
      errorBox.hidden = true;
    }
    if (!config) return;
    topWrap.hidden = !config.top;
    envWrap.hidden = !config.env;
    if (config.top) topSelect.value = appliedFilters[view].top;
    if (config.env) envSelect.value = appliedFilters[view].env;
  }

  function cancelChartRequest() {
    activeController?.abort();
    activeController = null;
    host.removeAttribute('aria-busy');
  }

  async function loadAndDraw(view, state) {
    cancelChartRequest();
    const key = cacheKey(view, state);
    if (cache.has(key)) {
      appliedFilters[view] = state;
      drawView(view);
      return;
    }
    const controller = new AbortController();
    activeController = controller;
    const url = new URL(data.query_url, location.href);
    url.searchParams.set('view', view);
    url.searchParams.set('top', state.top);
    url.searchParams.set('chart_env', state.env);
    host.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, {signal: controller.signal});
      if (controller.signal.aborted) return;
      if (response.status === 401) { location.assign('/cli-permission/login'); return; }
      if (response.redirected) { location.assign(response.url); return; }
      if (!response.ok) throw new Error('图表加载失败，请重试');
      const payload = await response.json();
      if (controller.signal.aborted) return;
      cache.set(key, payload.items || []);
      appliedFilters[view] = state;
      drawView(view);
    } catch (problem) {
      if (controller.signal.aborted) return;
      syncControls(view);
      if (errorBox) {
        errorBox.textContent = problem.message === 'Failed to fetch' ? '连接中断，原图表已保留，请重试' : problem.message;
        errorBox.hidden = false;
      }
    } finally {
      if (activeController === controller) {
        activeController = null;
        host.removeAttribute('aria-busy');
      }
    }
  }

  function render(view) {
    cancelChartRequest();
    active = view;
    buttons.forEach(button => {
      const selected = button.dataset.analysisView === view;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    description.textContent = labels[view];
    graphic.setAttribute('aria-label', `${buttons.find(button => button.dataset.analysisView === view).textContent}：${labels[view]}`);
    syncControls(view);
    drawView(view);
  }

  function onControlChange() {
    if (!viewControls[active]) return;
    const state = {
      top: viewControls[active].top ? topSelect.value : appliedFilters[active].top,
      env: lockedEnv || envSelect.value,
    };
    if (errorBox) {
      errorBox.textContent = '';
      errorBox.hidden = true;
    }
    loadAndDraw(active, state);
  }

  topSelect?.addEventListener('change', onControlChange);
  envSelect?.addEventListener('change', onControlChange);
  buttons.forEach(button => button.addEventListener('click', () => render(button.dataset.analysisView)));
  new ResizeObserver(() => {
    if (!graphic.clientWidth) return;
    drawView(active);
  }).observe(graphic);
  render(active);
}
