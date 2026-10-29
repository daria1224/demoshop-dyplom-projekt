const SESSION_STORAGE_KEY = 'demoshopSessionToken';
const LAST_ACTIVITY_STORAGE_KEY = 'demoshopLastActivityAt';
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;

function createSessionToken() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSessionToken() {
  const now = Date.now();
  let token = localStorage.getItem(SESSION_STORAGE_KEY);
  const lastActivityValue = localStorage.getItem(LAST_ACTIVITY_STORAGE_KEY);
  const lastActivityAt = Number(lastActivityValue);
  const sessionExpired = !lastActivityValue
    || !Number.isFinite(lastActivityAt)
    || now - lastActivityAt >= SESSION_TIMEOUT_MS;

  if (!token || sessionExpired) {
    token = createSessionToken();
    localStorage.setItem(SESSION_STORAGE_KEY, token);
  }

  return token;
}

function updateLastActivity() {
  localStorage.setItem(LAST_ACTIVITY_STORAGE_KEY, Date.now().toString());
}

function trackEvent(eventType, details = {}) {
  const sessionToken = getSessionToken();
  updateLastActivity();

  const event = {
    session_token: sessionToken,
    event_type: eventType,
    page: window.location.pathname,
    timestamp: new Date().toISOString(),
    ...details
  };
  console.log('[DemoShop event]', event);

  const apiEvent = { ...event };

  fetch('/api/events', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(apiEvent)
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`API zwróciło błąd HTTP ${response.status}.`);
      }
    })
    .catch(error => {
      console.error('Nie udało się wysłać zdarzenia do API:', error);
    });
}

function formatPrice(price) {
  return `${price.toFixed(2).replace('.', ',')} zł`;
}

const CART_STORAGE_KEY = 'demoshopCart';

function getCart() {
  try {
    const cart = JSON.parse(localStorage.getItem(CART_STORAGE_KEY));
    return Array.isArray(cart) ? cart : [];
  } catch {
    return [];
  }
}

function saveCart(cart) {
  localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
  updateCartCount(cart);
}

function updateCartCount(cart = getCart()) {
  const total = cart.reduce((sum, item) => sum + item.quantity, 0);

  document.querySelectorAll('.cart-count').forEach(item => {
    item.textContent = total;
  });
}

function addToCart(productId) {
  const cart = getCart();
  const line = cart.find(item => item.productId === productId);

  if (line) {
    line.quantity += 1;
  } else {
    cart.push({ productId, quantity: 1 });
  }

  saveCart(cart);
  return cart.reduce((sum, item) => sum + item.quantity, 0);
}

function illustration(product, large = false) {
  const artworks = {
    'kubek-aurora': `
      <path d="M63 54h50v52c0 12-10 21-25 21s-25-9-25-21V54Z"/>
      <path d="M113 67h13c13 0 13 30 0 30h-13M71 45c7-10 15 2 22-8 7 10 15-2 22 8" fill="none"/>
    `,
    'lampka-luna': `
      <path d="M53 91h70L99 39H77L53 91Z"/>
      <path d="M88 91v31M64 122h48" fill="none"/>
    `,
    'notes-moment': `
      <rect x="55" y="34" width="66" height="94" rx="6"/>
      <path d="M70 58h35M70 75h35M70 92h24" fill="none"/>
    `,
    'butelka-flow': `
      <path d="M72 42h32l-4 18 10 18v37c0 9-7 14-18 14h-8c-11 0-18-5-18-14V78l10-18-4-18Z"/>
      <path d="M78 42h20" fill="none"/>
    `,
    'wazon-nord': `
      <path d="M70 35h36l-5 39 13 35c4 12-5 20-18 20H80c-13 0-22-8-18-20l13-35-5-39Z"/>
      <path d="M78 48h20" fill="none"/>
    `,
    'podstawka-calm': `
      <ellipse cx="88" cy="91" rx="46" ry="32"/>
      <ellipse cx="88" cy="91" rx="29" ry="19" fill="none"/>
      <path d="M47 112h82" fill="none"/>
    `,
    'torba-weekend': `
      <rect x="47" y="61" width="82" height="65" rx="8"/>
      <path d="M69 61V48c0-9 7-14 19-14s19 5 19 14v13M47 80h82" fill="none"/>
    `,
    'dyfuzor-sora': `
      <path d="M65 84h46l8 35c2 7-4 11-11 11H68c-7 0-13-4-11-11l8-35Z"/>
      <path d="M78 84 61 37M88 84V31M98 84l18-47" fill="none"/>
    `
  };
  return `<div class="product-illustration ${product.color}${large ? ' large' : ''}" aria-label="Ilustracja: ${product.name}" role="img"><svg viewBox="0 0 176 160" aria-hidden="true">${artworks[product.id]}</svg></div>`;
}
function productCard(product) {
  return `
    <article class="product-card">
      ${illustration(product)}
      <div class="product-card-content">
        <p class="product-category">${product.category}</p>
        <h3>${product.name}</h3>
        <p class="product-description">${product.description}</p>
        <div class="card-bottom">
          <strong>${formatPrice(product.price)}</strong>
          <a class="button button-small" href="product.html?id=${product.id}" data-product-id="${product.id}">Zobacz produkt</a>
        </div>
      </div>
    </article>
  `;
}

function renderProducts() {
  const all = document.querySelector('.all-products');
  const featured = document.querySelector('.featured-products');

  if (all) all.innerHTML = products.map(productCard).join('');
  if (featured) featured.innerHTML = products.slice(0, 3).map(productCard).join('');
}

function renderProductDetail() {
  const target = document.querySelector('.product-detail');
  if (!target) return;

  const id = new URLSearchParams(window.location.search).get('id');
  const product = products.find(item => item.id === id) || products[0];

  document.title = `${product.name} — DemoShop`;
  document.querySelector('.breadcrumb-product').textContent = product.name;
  target.innerHTML = `
    <div>${illustration(product, true)}</div>
    <div class="detail-content">
      <p class="eyebrow">${product.category}</p>
      <h1>${product.name}</h1>
      <p class="detail-price">${formatPrice(product.price)}</p>
      <p class="detail-description">${product.description} Ten demonstracyjny produkt pozwala sprawdzić przejście do szczegółów oraz działanie przycisku koszyka.</p>
      <button class="button add-to-cart" type="button" data-product-id="${product.id}">Dodaj do koszyka</button>
      <p class="cart-message" role="status" aria-live="polite"></p>
    </div>
  `;
  trackEvent('view_item', { product_id: product.id, product_name: product.name });
}

function renderCart() {
  const target = document.querySelector('.cart-content');
  if (!target) return;

  const cart = getCart();
  if (!cart.length) {
    target.innerHTML = '<div class="empty-cart"><span>◌</span><h2>Koszyk jest pusty</h2><p>Dodaj produkt, który wpadł Ci w oko.</p><a class="button" href="products.html">Wróć do produktów</a></div>';
    return;
  }

  const rows = cart.map(line => {
    const product = products.find(item => item.id === line.productId);
    if (!product) return '';

    return `<article class="cart-item"><div class="cart-image">${illustration(product)}</div><div class="cart-product"><p class="product-category">${product.category}</p><h2>${product.name}</h2><p>${formatPrice(product.price)}</p></div><div class="quantity-control"><button type="button" data-cart-action="decrease" data-product-id="${product.id}" aria-label="Zmniejsz ilość">−</button><span>${line.quantity}</span><button type="button" data-cart-action="increase" data-product-id="${product.id}" aria-label="Zwiększ ilość">+</button></div><strong class="cart-line-total">${formatPrice(product.price * line.quantity)}</strong><button type="button" class="remove-item" data-cart-action="remove" data-product-id="${product.id}">Usuń</button></article>`;
  }).join('');
  const total = cart.reduce((sum, line) => {
    const product = products.find(item => item.id === line.productId);
    return sum + (product ? product.price * line.quantity : 0);
  }, 0);

  target.innerHTML = `<div class="cart-list">${rows}</div><div class="cart-summary"><span>Łączna wartość</span><strong>${formatPrice(total)}</strong></div><a class="button button-secondary" href="products.html">← Wróć do produktów</a>`;
}

function updateCartItem(productId, action) {
  let cart = getCart();
  const line = cart.find(item => item.productId === productId);
  if (!line) return;

  if (action === 'increase') line.quantity += 1;
  if (action === 'decrease') line.quantity -= 1;
  if (action === 'remove' || line.quantity < 1) {
    cart = cart.filter(item => item.productId !== productId);
  }

  saveCart(cart);
  renderCart();
  trackEvent('click', { element: `cart_${action}`, product_id: productId });
}

function setupMenu() {
  const button = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.main-nav');
  if (!button || !nav) return;

  button.addEventListener('click', () => {
    const open = nav.classList.toggle('is-open');
    button.setAttribute('aria-expanded', open);
    trackEvent('click', { element: 'mobile_menu', open });
  });
}

function setupInteractions() {
  updateCartCount();

  document.addEventListener('click', event => {
    const productLink = event.target.closest('[data-product-id]');
    if (productLink && productLink.matches('a')) {
      const product = products.find(item => item.id === productLink.dataset.productId);
      trackEvent('click', {
        element: 'view_product_button',
        product_id: product?.id,
        product_name: product?.name
      });
    }

    const addButton = event.target.closest('.add-to-cart');
    if (addButton) {
      const product = products.find(item => item.id === addButton.dataset.productId);
      const cartCount = addToCart(addButton.dataset.productId);

      document.querySelector('.cart-message').textContent = 'Produkt dodano do koszyka.';
      trackEvent('add_to_cart', {
        product_id: product?.id,
        product_name: product?.name,
        cart_count: cartCount
      });
    }

    const cartAction = event.target.closest('[data-cart-action]');
    if (cartAction) {
      updateCartItem(cartAction.dataset.productId, cartAction.dataset.cartAction);
    }

    const link = event.target.closest('a');
    if (link && !productLink) {
      trackEvent('click', {
        element: 'navigation_link',
        destination: link.getAttribute('href')
      });
    }
  });

  const form = document.querySelector('.contact-form');
  if (!form) return;

  form.addEventListener('submit', event => {
    event.preventDefault();

    const status = form.querySelector('.form-status');
    if (!form.checkValidity()) {
      status.textContent = 'Uzupełnij poprawnie wszystkie pola formularza.';
      form.reportValidity();
      return;
    }

    status.textContent = 'Dziękujemy! Wiadomość została zarejestrowana demonstracyjnie.';
    trackEvent('form_submit', { form: 'contact' });
    form.reset();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  getSessionToken();
  renderProducts();
  renderProductDetail();
  renderCart();
  setupMenu();
  setupInteractions();
  trackEvent('page_view', { title: document.title });
});
