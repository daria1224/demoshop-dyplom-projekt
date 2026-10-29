const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '..', 'js', 'main.js'),
  'utf8'
);

function trackingContext() {
  const requests = [];
  const storage = new Map();
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
      location: { pathname: '/products.html' }
    },
    document: {
      addEventListener() {},
      querySelector() { return null; },
      querySelectorAll() { return []; },
      title: 'Produkty — DemoShop'
    },
    URLSearchParams,
    products: []
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  return { context, requests };
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
