const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '..', 'js', 'main.js'),
  'utf8'
);

function trackingContext({ pathname = '/products.html', search = '', products = [] } = {}) {
  const requests = [];
  const storage = new Map();
  const classes = new Set();
  const productDetail = {
    innerHTML: '',
    classList: {
      add(value) { classes.add(value); },
      remove(value) { classes.delete(value); },
      contains(value) { return classes.has(value); }
    }
  };
  const breadcrumb = { textContent: '' };
  const context = {
    console: { log() {}, error() {} },
    fetch(url, options) {
      requests.push({ url, options });
      return Promise.resolve({ ok: true });
    },
    localStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, value); }
    },
    window: {
      crypto: { randomUUID: () => 'test-session-token' },
      location: { pathname, search }
    },
    document: {
      addEventListener() {},
      querySelector(selector) {
        if (selector === '.product-detail') return productDetail;
        if (selector === '.breadcrumb-product') return breadcrumb;
        return null;
      },
      querySelectorAll() { return []; },
      title: 'Produkt — DemoShop'
    },
    URLSearchParams,
    products
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  return { breadcrumb, context, productDetail, requests };
}

test('navigation click uses one keepalive request without retry', async () => {
  const { context, requests } = trackingContext();

  context.trackEvent('click', {
    element: 'navigation_link',
    destination: 'cart.html'
  });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, '/api/events');
  assert.equal(requests[0].options.keepalive, true);
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(
    JSON.parse(requests[0].options.body),
    {
      session_token: 'test-session-token',
      event_type: 'click',
      page: '/products.html',
      timestamp: JSON.parse(requests[0].options.body).timestamp,
      element: 'navigation_link',
      destination: 'cart.html'
    }
  );
});

const aurora = {
  id: 'kubek-aurora',
  name: 'Kubek Aurora',
  price: 49,
  category: 'Dom',
  color: 'peach',
  description: 'Ceramiczny kubek.'
};

test('existing product renders and records one view_item', () => {
  const { context, productDetail, requests } = trackingContext({
    pathname: '/product.html',
    search: '?id=kubek-aurora',
    products: [aurora]
  });

  context.renderProductDetail();

  assert.match(productDetail.innerHTML, /Kubek Aurora/);
  assert.match(productDetail.innerHTML, /add-to-cart/);
  assert.equal(requests.length, 1);
  const event = JSON.parse(requests[0].options.body);
  assert.equal(event.event_type, 'view_item');
  assert.equal(event.product_id, 'kubek-aurora');
});

test('unknown product shows a message without view_item or cart button', () => {
  const { breadcrumb, context, productDetail, requests } = trackingContext({
    pathname: '/product.html',
    search: '?id=nieistniejacy-produkt',
    products: [aurora]
  });

  context.renderProductDetail();

  assert.match(productDetail.innerHTML, /Nie znaleziono produktu/);
  assert.match(productDetail.innerHTML, /Wróć do produktów/);
  assert.doesNotMatch(productDetail.innerHTML, /add-to-cart/);
  assert.equal(breadcrumb.textContent, 'Nie znaleziono produktu');
  assert.equal(productDetail.classList.contains('product-detail-not-found'), true);
  assert.equal(requests.length, 0);
});

test('missing product id keeps the existing default product behavior', () => {
  const { context, productDetail, requests } = trackingContext({
    pathname: '/product.html',
    products: [aurora]
  });

  context.renderProductDetail();

  assert.match(productDetail.innerHTML, /Kubek Aurora/);
  assert.equal(requests.length, 1);
  assert.equal(JSON.parse(requests[0].options.body).event_type, 'view_item');
});
