'use strict';

const sections = {
  overview: {
    title: 'Przegląd',
    description: 'Miejsce, w którym aktywność odwiedzających nabiera znaczenia.',
    heading: 'Aktywność w jednym miejscu',
    detail: 'Tutaj pojawi się podsumowanie aktywności odwiedzających Twój sklep.',
    topics: [
      ['Podstawowe wskaźniki', 'Podsumowanie zdarzeń i zarejestrowanych sesji.'],
      ['Aktywność w czasie', 'Przebieg interakcji w kolejnych dniach.'],
      ['Najważniejsze obszary', 'Punkty wyjścia do szczegółowych zestawień.']
    ]
  },
  sessions: {
    title: 'Sesje',
    description: 'Zrozum, jak przebiegają zarejestrowane wizyty w DemoShop.',
    heading: 'Przebieg sesji',
    detail: 'Tutaj pojawią się zestawienia sesji i czasu zarejestrowanej aktywności.',
    topics: [
      ['Liczba sesji', 'Sesje zawierające co najmniej jedno zdarzenie.'],
      ['Czas aktywności', 'Odstęp między pierwszym a ostatnim zdarzeniem sesji.'],
      ['Zaangażowanie', 'Liczba zdarzeń przypadających na sesję.']
    ]
  },
  pages: {
    title: 'Strony i interakcje',
    description: 'Poznaj miejsca i elementy, z którymi wchodzą w interakcję odwiedzający.',
    heading: 'Ścieżki i kliknięcia',
    detail: 'Tutaj pojawią się zestawienia odsłon stron i klikanych elementów interfejsu.',
    topics: [
      ['Popularne podstrony', 'Odsłony zarejestrowane jako page_view.'],
      ['Klikane elementy', 'Interakcje z nawigacją i przyciskami.'],
      ['Kontekst interakcji', 'Strona i cel wybranego działania.']
    ]
  },
  products: {
    title: 'Produkty',
    description: 'Przyjrzyj się zainteresowaniu demonstracyjnym katalogiem produktów.',
    heading: 'Zainteresowanie produktami',
    detail: 'Tutaj pojawią się zestawienia wyświetleń produktów i dodań do koszyka.',
    topics: [
      ['Wyświetlenia produktów', 'Otwarcia stron szczegółów produktu.'],
      ['Dodania do koszyka', 'Zarejestrowane działania add_to_cart.'],
      ['Lejek interakcji', 'Przejścia od wyświetlenia produktu do jego dodania.']
    ]
  },
  events: {
    title: 'Zdarzenia',
    description: 'Zobacz, jakie działania składają się na aktywność w serwisie.',
    heading: 'Historia aktywności',
    detail: 'Tutaj pojawią się historia ostatnich zdarzeń i zestawienie ich typów.',
    topics: [
      ['Ostatnie zdarzenia', 'Chronologiczny przegląd zarejestrowanych działań.'],
      ['Typy zdarzeń', 'Odsłony, kliknięcia i pozostałe interakcje.'],
      ['Kontekst zdarzenia', 'Podstrona oraz powiązany element lub produkt.']
    ]
  }
};

async function authRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(path, {
      ...options,
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal
    });
    if (!response.ok) {
      const error = new Error('Żądanie nie powiodło się.');
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

function goToLogin() {
  window.location.replace('/dashboard/login');
}

function setupLogin() {
  const form = document.querySelector('#login-form');
  const fields = document.querySelector('#login-fields');
  const status = document.querySelector('#login-status');
  const label = document.querySelector('#login-button-label');
  const password = document.querySelector('#password');

  authRequest('/api/auth/status')
    .then(result => {
      if (result.authenticated) {
        window.location.replace('/dashboard');
        return;
      }
      status.hidden = true;
      fields.disabled = false;
    })
    .catch(() => {
      status.textContent = 'Nie udało się sprawdzić sesji. Możesz spróbować się zalogować.';
      status.classList.add('error');
      fields.disabled = false;
    });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (fields.disabled || !form.reportValidity()) return;
    fields.disabled = true;
    form.setAttribute('aria-busy', 'true');
    label.textContent = 'Logowanie…';
    status.hidden = false;
    status.classList.remove('error');
    status.textContent = 'Trwa logowanie…';

    try {
      await authRequest('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: document.querySelector('#username').value,
          password: password.value
        })
      });
      password.value = '';
      window.location.replace('/dashboard');
    } catch (error) {
      const messages = {
        401: 'Nieprawidłowy login lub hasło. Spróbuj ponownie.',
        403: 'Nie można zalogować się z tego adresu. Otwórz panel pod adresem serwera DemoShop.',
        422: 'Sprawdź poprawność danych logowania.',
        429: 'Zbyt wiele prób logowania. Odczekaj chwilę i spróbuj ponownie później.',
        503: 'Logowanie jest chwilowo niedostępne. Spróbuj ponownie później.'
      };
      status.textContent = messages[error.status] || 'Nie udało się połączyć z serwerem. Spróbuj ponownie.';
      status.classList.add('error');
      fields.disabled = false;
      password.value = '';
      password.focus();
    } finally {
      form.removeAttribute('aria-busy');
      label.textContent = 'Zaloguj się';
    }
  });
}

function setupDashboard() {
  const gate = document.querySelector('#session-gate');
  const shell = document.querySelector('#dashboard-shell');
  const retry = document.querySelector('#session-retry');
  const message = document.querySelector('#session-message');
  const spinner = document.querySelector('#session-spinner');
  const status = document.querySelector('#dashboard-status');
  const logout = document.querySelector('#logout-button');
  let checking = false;
  let authenticated = false;

  function showSection(moveFocus = false) {
    const requested = window.location.hash.slice(1);
    const key = Object.hasOwn(sections, requested) ? requested : 'overview';
    const section = sections[key];
    document.querySelector('#current-section').textContent = section.title;
    const title = document.querySelector('#section-title');
    title.textContent = section.title;
    document.querySelector('#section-description').textContent = section.description;
    document.querySelector('#panel-title').textContent = section.heading;
    document.querySelector('#panel-description').textContent = section.detail;
    document.querySelector('#panel-symbol').setAttribute('href', `#icon-${key}`);
    document.title = `${section.title} — DemoShop Analytics`;
    document.querySelectorAll('[data-section]').forEach(link => {
      if (link.dataset.section === key) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    const topics = document.querySelector('#section-topics');
    topics.replaceChildren();
    section.topics.forEach(([heading, description], index) => {
      const card = document.createElement('article');
      card.className = 'topic-card';
      const number = document.createElement('span');
      number.className = 'topic-number';
      number.textContent = `0${index + 1}`;
      const cardTitle = document.createElement('h3');
      cardTitle.textContent = heading;
      const detail = document.createElement('p');
      detail.textContent = description;
      card.append(number, cardTitle, detail);
      topics.append(card);
    });
    if (moveFocus && authenticated) title.focus();
  }

  async function checkSession() {
    if (checking) return;
    checking = true;
    retry.hidden = true;
    spinner.hidden = false;
    message.textContent = 'Sprawdzanie sesji właściciela…';
    try {
      const result = await authRequest('/api/auth/status');
      if (!result.authenticated) {
        authenticated = false;
        shell.hidden = true;
        goToLogin();
        return;
      }
      authenticated = true;
      showSection();
      gate.hidden = true;
      shell.hidden = false;
    } catch {
      authenticated = false;
      shell.hidden = true;
      gate.hidden = false;
      spinner.hidden = true;
      message.textContent = 'Nie udało się połączyć z serwerem. Sprawdź połączenie i spróbuj ponownie.';
      retry.hidden = false;
    } finally {
      checking = false;
    }
  }

  logout.addEventListener('click', async () => {
    logout.disabled = true;
    logout.textContent = 'Wylogowywanie…';
    status.hidden = true;
    try {
      await authRequest('/api/auth/logout', { method: 'POST' });
      authenticated = false;
      shell.hidden = true;
      goToLogin();
    } catch (error) {
      if (error.status === 401) {
        authenticated = false;
        shell.hidden = true;
        goToLogin();
        return;
      }
      status.textContent = 'Nie udało się wylogować. Spróbuj ponownie. Sesja mogła pozostać aktywna.';
      status.hidden = false;
      logout.disabled = false;
      logout.textContent = 'Wyloguj się';
    }
  });

  retry.addEventListener('click', checkSession);
  window.addEventListener('hashchange', () => {
    showSection(true);
    checkSession();
  });
  window.addEventListener('focus', checkSession);
  window.addEventListener('pageshow', checkSession);
  window.addEventListener('pagehide', () => {
    shell.hidden = true;
    gate.hidden = false;
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkSession();
  });
  setInterval(() => {
    if (!document.hidden) checkSession();
  }, 60000);
  checkSession();
}

if (document.body.dataset.page === 'login') setupLogin();
if (document.body.dataset.page === 'dashboard') setupDashboard();
