const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');
const {countScale} = require('../app/static/chart-scale.js');

const source = readFileSync(join(__dirname, '../app/static/analytics.js'), 'utf8');
const point = label => ({label, value: 1, href: ''});

class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.classList = {toggle() {}, add() {}};
    this.clientWidth = 1200;
    this.width = {baseVal: {value: 0}};
  }

  appendChild(node) { this.children.push(node); return node; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  querySelector(tag) { return this.children.find(node => node.tag === tag) || null; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  removeAttribute(name) { delete this.attributes[name]; }
  getComputedTextLength() { return 50; }

  setAttribute(name, value) {
    this.attributes[name] = value;
    if (name === 'width') this.width.baseVal.value = Number(value);
  }
}

function dashboard() {
  const host = new Element();
  const graphic = new Element();
  const top = new Element();
  const error = new Element();
  const controls = {
    '.analytics-plot-graphic': graphic,
    '.analytics-plot-legend': new Element(),
    '.analytics-scroll-hint': new Element(),
    '[data-analysis-controls]': new Element(),
    '[data-analysis-top-wrap]': new Element(),
    '[data-analysis-env-wrap]': new Element(),
    '[data-analysis-top]': top,
    '[data-analysis-env]': new Element(),
    '[data-analysis-error]': error,
  };
  host.querySelector = selector => controls[selector];
  host.dataset.analysisChart = JSON.stringify({
    query_url: '/chart', points: [], commands: [],
    distribution: [point('TOP10')], ranking: [point('ranking')], versions: [point('versions')],
  });
  const buttons = ['commands', 'distribution', 'ranking'].map(view => {
    const button = new Element('button');
    button.dataset.analysisView = view;
    button.textContent = view;
    return button;
  });
  const requests = [];
  runInNewContext(source, {
    AbortController, URL, countScale,
    location: {href: 'http://localhost/analytics'},
    ResizeObserver: class { observe() {} },
    document: {
      querySelector: selector => ({
        '[data-analysis-chart]': host, '[data-analysis-description]': new Element(),
      })[selector],
      querySelectorAll: () => buttons,
      createElement: tag => new Element(tag),
      createElementNS: (_namespace, tag) => new Element(tag),
      createTextNode: content => Object.assign(new Element('#text'), {textContent: content}),
    },
    // Let a stubbed response settle even after cancellation to exercise the response guard.
    fetch: (url, {signal}) => new Promise(resolve => requests.push({url, signal, resolve})),
  });
  return {
    top, error, host, requests,
    open(view) { buttons.find(button => button.dataset.analysisView === view).listeners.click(); },
    chooseTop(value) { top.value = value; top.listeners.change(); },
    chartTitle() { return graphic.querySelector('svg').querySelector('g').querySelector('title').textContent; },
  };
}

async function respond(request, label) {
  request.resolve(label
    ? {ok: true, json: async () => ({items: [point(label)]})}
    : {ok: false, status: 500});
  await new Promise(resolve => setImmediate(resolve));
}

test('returning to a cached filter cancels a pending request and ignores its response', async () => {
  const page = dashboard();
  page.open('distribution');
  page.chooseTop('20');
  const [pending] = page.requests;
  assert.equal(pending.url.searchParams.get('top'), '20');
  page.chooseTop('10');
  await respond(pending, 'late TOP20');
  assert.equal(pending.signal.aborted, true);
  assert.equal(page.requests.length, 1);
  assert.equal(page.host.attributes['aria-busy'], undefined);
  assert.equal(page.top.value, '10');
  assert.match(page.chartTitle(), /^TOP10：/);
});

test('a failed request from a previous view cannot show an error in the active view', async () => {
  const page = dashboard();
  page.open('distribution');
  page.chooseTop('20');
  page.open('ranking');
  await respond(page.requests[0]);
  assert.equal(page.error.hidden, true);
  assert.equal(page.host.attributes['aria-busy'], undefined);
  assert.match(page.chartTitle(), /^ranking：/);
  page.open('distribution');
  assert.equal(page.top.value, '10');
  assert.equal(page.requests.length, 1);
});

test('a failed request restores the last displayed filter after rapid changes', async () => {
  const page = dashboard();
  page.open('distribution');
  page.chooseTop('20');
  await respond(page.requests[0], 'TOP20');
  page.chooseTop('30');
  page.chooseTop('50');
  await respond(page.requests[1], 'late TOP30');
  assert.equal(page.host.attributes['aria-busy'], 'true');
  await respond(page.requests[2]);
  assert.equal(page.top.value, '20');
  assert.match(page.chartTitle(), /^TOP20：/);
  assert.match(page.error.textContent, /图表加载失败/);
  assert.equal(page.error.hidden, false);
  assert.equal(page.host.attributes['aria-busy'], undefined);
});
