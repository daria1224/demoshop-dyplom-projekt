'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  aggregatePageViews,
  buildActivityChartConfig,
  buildDateQuery,
  buildEventsChartConfig,
  buildPagesChartConfig,
  buildPagesDetailChartConfig,
  buildProductRankings,
  buildSessionMetrics,
  calculateSingleEventShare,
  chartInstances,
  destroyChart,
  destroyCharts,
  formatDuration,
  formatInteractionElement,
  formatInteractionTarget,
  getPagesAndClicksTotals,
  getProductEventTotals,
  getVisibleClickRows,
  hasSessionData,
  loadSessionAnalytics,
  loadOverviewAnalytics,
  loadPagesAnalytics,
  loadProductAnalytics,
  needsDashboardRender,
  normalizeDemoShopPage,
  normalizeFunnelData,
  prepareClickRows,
  prepareProductRows,
  replaceChart,
  validateDateRange
} = require('../dashboard/assets/dashboard.js');

test('statystyki produktów sumują zdarzenia i tworzą niezależne rankingi', () => {
  const rows = [
    { product_id: 'a', product_name: 'Kubek Aurora', view_count: 8, add_to_cart_count: 2 },
    { product_id: 'b', product_name: 'Lampka Luna', view_count: 3, add_to_cart_count: 5 },
    { product_id: 'c', product_name: '', view_count: 1, add_to_cart_count: 0 }
  ];
  assert.deepEqual(getProductEventTotals(rows), { views: 12, addToCart: 7 });
  const rankings = buildProductRankings(rows);
  assert.equal(rankings.views[0].product_name, 'Kubek Aurora');
  assert.equal(rankings.cart[0].product_name, 'Lampka Luna');
  assert.equal(rankings.cart.length, 2);
  assert.equal(prepareProductRows(rows)[2].product_name, 'Produkt bez nazwy');
});

test('lejek zachowuje pary sesja–produkt i nie utożsamia ich ze zdarzeniami', () => {
  const funnel = normalizeFunnelData({
    viewed_session_product_pairs: 3,
    converted_session_product_pairs: 1,
    conversion_rate_percent: 33.3,
    products: [{
      product_id: 'kubek-aurora',
      product_name: 'Kubek Aurora',
      viewed_session_product_pairs: 2,
      converted_session_product_pairs: 1,
      conversion_rate_percent: 50
    }]
  });
  assert.equal(funnel.viewedPairs, 3);
  assert.equal(funnel.convertedPairs, 1);
  assert.equal(funnel.products[0].conversionRate, 50);
  assert.notEqual(funnel.viewedPairs, 8);
});

test('pusty lejek ma bezpieczne wartości zerowe', () => {
  assert.deepEqual(normalizeFunnelData({}), {
    viewedPairs: 0,
    convertedPairs: 0,
    conversionRate: 0,
    products: []
  });
});

test('loadProductAnalytics przekazuje ten sam filtr do produktów i lejka', async () => {
  const calls = [];
  const request = async path => {
    calls.push(path);
    return path.includes('/products') ? [] : { products: [] };
  };
  const result = await loadProductAnalytics(
    { dateFrom: '2026-04-01', dateTo: '2026-04-03' },
    request
  );
  assert.deepEqual(result.products, []);
  assert.equal(calls.length, 2);
  assert.ok(calls.every(path => path.endsWith('?date_from=2026-04-01&date_to=2026-04-03')));
});

test('loadProductAnalytics przekazuje 401, błąd sieci i anulowanie żądania', async () => {
  const unauthorized = Object.assign(new Error('unauthorized'), { status: 401 });
  await assert.rejects(
    loadProductAnalytics({ dateFrom: '', dateTo: '' }, async () => { throw unauthorized; }),
    error => error.status === 401
  );
  await assert.rejects(
    loadProductAnalytics({ dateFrom: '', dateTo: '' }, async () => { throw new Error('network'); }),
    /network/
  );

  const controller = new AbortController();
  const pending = loadProductAnalytics(
    { dateFrom: '', dateTo: '' },
    (path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    }),
    controller.signal
  );
  controller.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
});

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

test('formatowanie czasu sesji obsługuje sekundy, minuty i wartości puste', () => {
  assert.equal(formatDuration(0), '0 s');
  assert.equal(formatDuration(45), '45 s');
  assert.equal(formatDuration(60), '1 min');
  assert.equal(formatDuration(135), '2 min 15 s');
  assert.equal(formatDuration(undefined), '0 s');
});

test('metryki sesji odpowiadają polom API i czytelnie prezentują zera', () => {
  const metrics = buildSessionMetrics({
    session_count: 4,
    average_activity_duration_seconds: 135,
    median_activity_duration_seconds: 45,
    average_events_per_session: 2.5,
    single_event_session_count: 1
  });
  assert.deepEqual(metrics.map(metric => metric[1]), ['4', '2 min 15 s', '45 s', '2,5', '1']);

  const emptyMetrics = buildSessionMetrics({});
  assert.deepEqual(emptyMetrics.map(metric => metric[1]), ['0', '0 s', '0 s', '0', '0']);
});

test('udział sesji z jednym zdarzeniem nie dzieli przez zero', () => {
  assert.equal(calculateSingleEventShare(4, 1), 25);
  assert.equal(calculateSingleEventShare(3, 1), 33.3);
  assert.equal(calculateSingleEventShare(0, 0), 0);
  assert.equal(calculateSingleEventShare(undefined, undefined), 0);
});

test('pusta odpowiedź sesji jest rozpoznawana bez błędu', () => {
  assert.equal(hasSessionData({ session_count: 1 }), true);
  assert.equal(hasSessionData({ session_count: 0 }), false);
  assert.equal(hasSessionData({}), false);
  assert.equal(hasSessionData(null), false);
});

test('loadSessionAnalytics przekazuje filtry, błędy i sygnał anulowania', async () => {
  const calls = [];
  const controller = new AbortController();
  const result = await loadSessionAnalytics(
    { dateFrom: '2026-02-01', dateTo: '2026-02-05' },
    async (path, options) => {
      calls.push([path, options.signal]);
      return { session_count: 2 };
    },
    controller.signal
  );
  assert.equal(result.session_count, 2);
  assert.equal(calls[0][0], '/api/analytics/sessions?date_from=2026-02-01&date_to=2026-02-05');
  assert.equal(calls[0][1], controller.signal);

  const unauthorized = Object.assign(new Error('unauthorized'), { status: 401 });
  await assert.rejects(
    loadSessionAnalytics({ dateFrom: '', dateTo: '' }, async () => { throw unauthorized; }),
    error => error.status === 401
  );

  const delayedController = new AbortController();
  const pending = loadSessionAnalytics(
    { dateFrom: '', dateTo: '' },
    (path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    }),
    delayedController.signal
  );
  delayedController.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
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
    ['products.html', 'Produkty'],
    ['/C:/Users/Test/Documents/ChatGPT/demoshop/index.html', 'Strona główna'],
    ['C:\\Users\\Test\\Documents\\ChatGPT\\demoshop\\cart.html', 'Koszyk']
  ]);
  expected.forEach((label, path) => assert.equal(normalizeDemoShopPage(path).label, label));
  assert.equal(normalizeDemoShopPage('/foreign/index.html').label, null);
  assert.equal(normalizeDemoShopPage('/another-shop/cart.html').label, null);
});

test('szczegółowy wykres stron wykorzystuje pełny zagregowany ranking', () => {
  const rows = [
    { page: '/', view_count: 2 },
    { page: '/index.html', view_count: 3 },
    { page: '/products.html', view_count: 4 },
    { page: '/cart.html', view_count: 1 }
  ];
  const chart = buildPagesDetailChartConfig(rows);
  assert.equal(chart.type, 'bar');
  assert.equal(chart.options.indexAxis, 'y');
  assert.deepEqual(chart.data.labels, ['Strona główna', 'Produkty', 'Koszyk']);
  assert.deepEqual(chart.data.datasets[0].data, [5, 4, 1]);
});

test('kliknięcia otrzymują czytelne i bezpieczne etykiety', () => {
  const rows = prepareClickRows([
    { page: '/products.html', element: 'view_product_button', target: 'kubek-aurora', click_count: 4 },
    { page: '/index.html', element: 'navigation_link', target: 'products.html', click_count: 6 },
    { page: '/C:/Users/Test/private/secret.html', element: 'custom_action', target: '/private/target', click_count: 2 },
    { page: '/other/private.html', element: 'unknown', target: null, click_count: 1 }
  ]);
  assert.deepEqual(rows.map(row => row.click_count), [6, 4, 2, 1]);
  assert.deepEqual(rows[0], {
    page: 'Strona główna',
    element: 'Link nawigacyjny',
    target: 'Produkty',
    click_count: 6
  });
  assert.equal(rows[1].element, 'Zobacz produkt');
  assert.equal(rows[1].target, 'Kubek aurora');
  assert.equal(rows[2].element, 'Custom action');
  assert.equal(rows[2].target, 'Inny cel');
  assert.equal(rows[3].element, 'Nieznany element');
  assert.equal(rows[3].target, '—');
  assert.equal(JSON.stringify(rows).includes('Users'), false);
  assert.equal(JSON.stringify(rows).includes('private'), false);
  assert.equal(formatInteractionElement('cart_remove'), 'Usunięcie produktu z koszyka');
  assert.equal(formatInteractionTarget('/contact.html'), 'Kontakt');
});

test('sumy odsłon i kliknięć wynikają z obu odpowiedzi API', () => {
  assert.deepEqual(
    getPagesAndClicksTotals(
      [{ page: '/', view_count: 3 }, { page: '/index.html', view_count: 2 }],
      [{ click_count: 4 }, { click_count: 1 }]
    ),
    { pageViews: 5, clicks: 5 }
  );
  assert.deepEqual(getPagesAndClicksTotals([], []), { pageViews: 0, clicks: 0 });
});

test('ranking interakcji domyślnie ogranicza widok do dziesięciu pozycji', () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({ click_count: 12 - index }));
  assert.equal(getVisibleClickRows(rows).length, 10);
  assert.equal(getVisibleClickRows(rows, true).length, 12);
});

test('loadPagesAnalytics stosuje jeden filtr i obsługuje 401 oraz anulowanie', async () => {
  const calls = [];
  const controller = new AbortController();
  const data = await loadPagesAnalytics(
    { dateFrom: '2026-03-01', dateTo: '2026-03-05' },
    async (path, options) => {
      calls.push([path, options.signal]);
      return path.includes('/pages') ? [{ page: '/', view_count: 2 }] : [{ click_count: 1 }];
    },
    controller.signal
  );
  assert.equal(data.pages[0].view_count, 2);
  assert.equal(data.clicks[0].click_count, 1);
  assert.deepEqual(calls.map(call => call[0]), [
    '/api/analytics/pages?date_from=2026-03-01&date_to=2026-03-05',
    '/api/analytics/clicks?date_from=2026-03-01&date_to=2026-03-05'
  ]);
  assert.ok(calls.every(call => call[1] === controller.signal));

  const unauthorized = Object.assign(new Error('unauthorized'), { status: 401 });
  await assert.rejects(
    loadPagesAnalytics({ dateFrom: '', dateTo: '' }, async () => { throw unauthorized; }),
    error => error.status === 401
  );

  const delayedController = new AbortController();
  const pending = loadPagesAnalytics(
    { dateFrom: '', dateTo: '' },
    (path, options) => new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    }),
    delayedController.signal
  );
  delayedController.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
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
