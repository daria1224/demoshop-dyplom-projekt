'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  aggregatePageViews,
  buildActivityChartConfig,
  buildDateQuery,
  buildEventsChartConfig,
  buildPagesChartConfig,
  chartInstances,
  destroyChart,
  destroyCharts,
  loadOverviewAnalytics,
  needsDashboardRender,
  normalizeDemoShopPage,
  replaceChart,
  validateDateRange
} = require('../dashboard/assets/dashboard.js');

test('buildDateQuery tworzy wspólny zakres dla wszystkich endpointów', () => {
  assert.equal(buildDateQuery('', ''), '');
  assert.equal(
    buildDateQuery('2026-01-02', '2026-01-05'),
    '?date_from=2026-01-02&date_to=2026-01-05'
  );
  assert.equal(buildDateQuery('2026-01-02', ''), '?date_from=2026-01-02');
});

test('validateDateRange odrzuca odwrócony zakres', () => {
  assert.equal(validateDateRange('2026-02-02', '2026-02-01'), 'Data „Od” nie może być późniejsza niż data „Do”.');
  assert.equal(validateDateRange('2026-02-01', '2026-02-01'), '');
  assert.equal(validateDateRange('', ''), '');
});

test('konfiguracje Chart.js odwzorowują małe i puste zbiory', () => {
  const activity = buildActivityChartConfig([
    { date: '2026-01-01', event_count: 1 },
    { date: '2026-01-02', event_count: 2 }
  ]);
  assert.equal(activity.type, 'line');
  assert.deepEqual(activity.data.labels, ['2026-01-01', '2026-01-02']);
  assert.deepEqual(activity.data.datasets[0].data, [1, 2]);
  assert.equal(activity.options.scales.y.ticks.precision, 0);
  assert.deepEqual(buildActivityChartConfig([]).data.datasets[0].data, []);

  const events = buildEventsChartConfig([
    { event_type: 'page_view', event_count: 3 },
    { event_type: 'click', event_count: 1 },
    { event_type: 'form_submit', event_count: 0 }
  ]);
  assert.equal(events.type, 'bar');
  assert.equal(events.options.indexAxis, 'y');
  assert.equal(events.options.animation, false);
  assert.deepEqual(events.data.labels, ['Odsłony stron', 'Kliknięcia', 'Wysłania formularza']);
  assert.deepEqual(events.data.datasets[0].data, [3, 1, 0]);
  assert.equal(events.data.datasets[0].barThickness, 8);
  assert.equal(events.plugins[0].id, 'eventValueLabels');

  const pages = buildPagesChartConfig([
    { page: '/', view_count: 4 },
    { page: '/index.html', view_count: 5 },
    { page: '/C:/Users/Test/Documents/ChatGPT/demoshop/index.html', view_count: 3 },
    { page: '/products.html', view_count: 6 },
    { page: '/cart.html', view_count: 2 }
  ]);
  assert.equal(pages.type, 'bar');
  assert.equal(pages.options.indexAxis, 'y');
  assert.deepEqual(pages.data.labels, ['Strona główna', 'Produkty', 'Koszyk']);
  assert.deepEqual(pages.data.datasets[0].data, [12, 6, 2]);
  assert.equal(buildPagesChartConfig([]).data.labels.length, 0);
});

test('normalizacja mapuje sześć stron DemoShop i ostrożne ścieżki historyczne', () => {
  const expected = new Map([
    ['/', 'Strona główna'],
    ['/index.html', 'Strona główna'],
    ['/products.html', 'Produkty'],
    ['/product.html', 'Szczegóły produktu'],
    ['/cart.html', 'Koszyk'],
    ['/about.html', 'O nas'],
    ['/contact.html', 'Kontakt'],
    ['/C:/Users/Test/Documents/ChatGPT/demoshop/index.html', 'Strona główna'],
    ['C:\\Users\\Test\\Documents\\ChatGPT\\demoshop\\cart.html', 'Koszyk']
  ]);
  expected.forEach((label, path) => assert.equal(normalizeDemoShopPage(path).label, label));
  assert.equal(normalizeDemoShopPage('/foreign/index.html').label, null);
  assert.equal(normalizeDemoShopPage('/another-shop/cart.html').label, null);
});

test('ranking agreguje odpowiedniki przed sortowaniem i nie ujawnia lokalnych ścieżek', () => {
  const result = aggregatePageViews([
    { page: '/products.html', view_count: 6 },
    { page: '/', view_count: 4 },
    { page: '/index.html', view_count: 5 },
    { page: '/C:/Users/Test/Documents/ChatGPT/demoshop/index.html', view_count: 3 },
    { page: '/cart.html', view_count: 2 },
    { page: '/private/local/secret.html', view_count: 7 }
  ]);
  assert.deepEqual(result.map(page => [page.label, page.view_count]), [
    ['Strona główna', 12],
    ['Inna strona', 7],
    ['Produkty', 6],
    ['Koszyk', 2]
  ]);
  assert.equal(JSON.stringify(result).includes('Users'), false);
  assert.equal(JSON.stringify(result.map(page => page.label)).includes('private'), false);
});

test('cykliczna kontrola aktywnej sesji nie inicjuje ponownie Dashboardu', () => {
  assert.equal(needsDashboardRender(false, true), true);
  assert.equal(needsDashboardRender(true, true), true);
  assert.equal(needsDashboardRender(true, false), false);
});

test('ponowne renderowanie niszczy poprzednią instancję Chart.js', () => {
  class FakeChart {
    constructor(canvas, config) {
      this.canvas = canvas;
      this.config = config;
      this.destroyed = false;
    }
    destroy() {
      this.destroyed = true;
    }
  }

  const first = replaceChart('activity', {}, { type: 'line' }, FakeChart);
  const second = replaceChart('activity', {}, { type: 'line' }, FakeChart);
  assert.equal(first.destroyed, true);
  assert.equal(second.destroyed, false);
  assert.equal(chartInstances.activity, second);
  destroyChart('activity');
  assert.equal(second.destroyed, true);
  assert.equal(chartInstances.activity, undefined);

  const third = replaceChart('pages', {}, { type: 'bar' }, FakeChart);
  destroyCharts();
  assert.equal(third.destroyed, true);
  assert.equal(chartInstances.pages, undefined);
});

test('loadOverviewAnalytics pobiera rzeczywiste struktury pięciu endpointów', async () => {
  const responses = {
    summary: { total_events: 8, total_sessions: 2, page_views: 3, clicks: 2, product_views: 2, add_to_cart: 1 },
    sessions: { average_events_per_session: 4, average_activity_duration_seconds: 30 },
    activity: [{ date: '2026-01-02', event_count: 8 }],
    events: [{ event_type: 'page_view', event_count: 3 }],
    pages: [{ page: '/products.html', view_count: 3 }]
  };
  const calls = [];
  const request = async path => {
    calls.push(path);
    const endpoint = path.match(/analytics\/([^?]+)/)[1];
    return responses[endpoint];
  };
  const result = await loadOverviewAnalytics(
    { dateFrom: '2026-01-02', dateTo: '2026-01-03' },
    request
  );
  assert.equal(result.summary.total_events, 8);
  assert.equal(result.activity[0].event_count, 8);
  assert.equal(calls.length, 5);
  assert.ok(calls.every(path => path.endsWith('?date_from=2026-01-02&date_to=2026-01-03')));
});

test('loadOverviewAnalytics przekazuje błędy HTTP i nie ukrywa 401', async () => {
  const error = Object.assign(new Error('unauthorized'), { status: 401 });
  await assert.rejects(
    loadOverviewAnalytics({ dateFrom: '', dateTo: '' }, async () => { throw error; }),
    candidate => candidate.status === 401
  );
});

test('nowsze wywołanie może anulować starsze przez AbortSignal', async () => {
  const controller = new AbortController();
  const request = (path, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => {
      const error = new Error('aborted');
      error.name = 'AbortError';
      reject(error);
    });
  });
  const pending = loadOverviewAnalytics(
    { dateFrom: '', dateTo: '' },
    request,
    controller.signal
  );
  controller.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
});
