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

const eventLabels = {
  page_view: 'Odsłony stron',
  click: 'Kliknięcia',
  view_item: 'Wyświetlenia produktów',
  add_to_cart: 'Dodania do koszyka',
  form_submit: 'Wysłania formularza'
};

const numberFormatter = new Intl.NumberFormat('pl-PL');
const chartInstances = {};
const pageDefinitions = {
  '/': { key: 'home', label: 'Strona główna' },
  '/index.html': { key: 'home', label: 'Strona główna' },
  '/products.html': { key: 'products', label: 'Produkty' },
  '/product.html': { key: 'product', label: 'Szczegóły produktu' },
  '/cart.html': { key: 'cart', label: 'Koszyk' },
  '/about.html': { key: 'about', label: 'O nas' },
  '/contact.html': { key: 'contact', label: 'Kontakt' }
};

function buildDateQuery(dateFrom = '', dateTo = '') {
  const parameters = new URLSearchParams();
  if (dateFrom) parameters.set('date_from', dateFrom);
  if (dateTo) parameters.set('date_to', dateTo);
  const query = parameters.toString();
  return query ? `?${query}` : '';
}

function validateDateRange(dateFrom, dateTo) {
  if (dateFrom && dateTo && dateFrom > dateTo) {
    return 'Data „Od” nie może być późniejsza niż data „Do”.';
  }
  return '';
}

function needsDashboardRender(authenticated, shellHidden) {
  return !authenticated || shellHidden;
}

function formatNumber(value) {
  return numberFormatter.format(Number(value) || 0);
}

function formatDuration(value) {
  const seconds = Math.max(0, Math.round(Number(value) || 0));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes} min ${remainder} s` : `${minutes} min`;
}

function calculateSingleEventShare(sessionCount, singleEventSessionCount) {
  const total = Math.max(0, Number(sessionCount) || 0);
  const single = Math.max(0, Number(singleEventSessionCount) || 0);
  return total ? Math.min(100, Math.round((single / total) * 1000) / 10) : 0;
}

function hasSessionData(data) {
  return Number(data?.session_count) > 0;
}

function buildSessionMetrics(data) {
  return [
    ['Liczba sesji', formatNumber(data.session_count), 'Sesje z aktywnością w zakresie'],
    ['Średni czas aktywności', formatDuration(data.average_activity_duration_seconds), 'Między pierwszym i ostatnim zdarzeniem'],
    ['Mediana czasu aktywności', formatDuration(data.median_activity_duration_seconds), 'Środkowa wartość czasu aktywności'],
    ['Średnia zdarzeń na sesję', formatNumber(data.average_events_per_session), 'Zdarzenia w wybranym zakresie'],
    ['Sesje z jednym zdarzeniem', formatNumber(data.single_event_session_count), 'Czas aktywności takiej sesji wynosi 0 s']
  ];
}

function normalizeDemoShopPage(value) {
  const rawPath = typeof value === 'string' ? value.trim().replaceAll('\\', '/') : '';
  const pathWithoutParameters = rawPath.split(/[?#]/, 1)[0];
  const normalizedPath = pathWithoutParameters.length > 1
    ? pathWithoutParameters.replace(/\/+$/, '')
    : pathWithoutParameters;
  const directMatch = pageDefinitions[normalizedPath.toLowerCase()];
  if (directMatch) return directMatch;

  const historicalMatch = normalizedPath.match(
    /(?:^|\/)demoshop\/(index|products|product|cart|about|contact)\.html$/i
  );
  if (historicalMatch) {
    return pageDefinitions[`/${historicalMatch[1].toLowerCase()}.html`];
  }

  return { key: `unknown:${normalizedPath}`, label: null };
}

function aggregatePageViews(rows) {
  const pages = new Map();
  rows.forEach(row => {
    const normalized = normalizeDemoShopPage(row.page);
    const existing = pages.get(normalized.key) || {
      key: normalized.key,
      label: normalized.label,
      view_count: 0
    };
    existing.view_count += Number(row.view_count) || 0;
    pages.set(normalized.key, existing);
  });

  const sorted = [...pages.values()].sort((first, second) => (
    second.view_count - first.view_count
    || (first.label || '').localeCompare(second.label || '', 'pl')
    || first.key.localeCompare(second.key)
  ));
  let unknownIndex = 0;
  return sorted.map(page => {
    if (page.label) {
      return { label: page.label, view_count: page.view_count };
    }
    unknownIndex += 1;
    return {
      label: sorted.filter(item => !item.label).length === 1
        ? 'Inna strona'
        : `Inna strona ${unknownIndex}`,
      view_count: page.view_count
    };
  });
}

function buildActivityChartConfig(rows) {
  return {
    type: 'line',
    data: {
      labels: rows.map(row => row.date),
      datasets: [{
        label: 'Zdarzenia',
        data: rows.map(row => Number(row.event_count) || 0),
        borderColor: '#186c60',
        backgroundColor: 'rgba(24, 108, 96, .12)',
        pointBackgroundColor: '#ffffff',
        pointBorderColor: '#186c60',
        pointBorderWidth: 2,
        pointRadius: rows.length < 3 ? 5 : 3,
        pointHoverRadius: 6,
        borderWidth: 2,
        fill: true,
        tension: rows.length < 3 ? 0 : .28
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: context => `Zdarzenia: ${formatNumber(context.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#647780', maxRotation: 0, autoSkip: true, maxTicksLimit: 7 }
        },
        y: {
          beginAtZero: true,
          grid: { color: '#edf1ef' },
          ticks: { color: '#647780', precision: 0 }
        }
      }
    }
  };
}

function buildEventsChartConfig(rows) {
  const valuePlugin = {
    id: 'eventValueLabels',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      const metadata = chart.getDatasetMeta(0);
      ctx.save();
      ctx.fillStyle = '#edf2ef';
      metadata.data.forEach(bar => {
        ctx.beginPath();
        ctx.roundRect(chartArea.left, bar.y - 4, chartArea.width, 8, 4);
        ctx.fill();
      });
      ctx.restore();
    },
    afterDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      const metadata = chart.getDatasetMeta(0);
      ctx.save();
      ctx.fillStyle = '#172d35';
      ctx.font = '600 11px "Segoe UI", Arial, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      metadata.data.forEach((bar, index) => {
        ctx.fillText(formatNumber(chart.data.datasets[0].data[index]), chartArea.right + 9, bar.y);
      });
      ctx.restore();
    }
  };
  return {
    type: 'bar',
    data: {
      labels: rows.map(row => eventLabels[row.event_type] || row.event_type),
      datasets: [{
        label: 'Zdarzenia',
        data: rows.map(row => Number(row.event_count) || 0),
        backgroundColor: '#6f9c84',
        hoverBackgroundColor: '#186c60',
        borderRadius: 5,
        borderSkipped: false,
        barThickness: 8
      }]
    },
    plugins: [valuePlugin],
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { right: 55 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: context => `Zdarzenia: ${formatNumber(context.parsed.x)}`
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          display: false,
          suggestedMax: Math.max(1, ...rows.map(row => Number(row.event_count) || 0))
        },
        y: {
          grid: { display: false },
          border: { display: false },
          ticks: { color: '#172d35', padding: 10 }
        }
      }
    }
  };
}

function buildPagesChartConfig(rows) {
  const visibleRows = aggregatePageViews(rows).slice(0, 6);
  return {
    type: 'bar',
    data: {
      labels: visibleRows.map(row => row.label),
      datasets: [{
        label: 'Odsłony',
        data: visibleRows.map(row => Number(row.view_count) || 0),
        backgroundColor: '#6f9c84',
        hoverBackgroundColor: '#186c60',
        borderRadius: 5,
        borderSkipped: false,
        barThickness: 17
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: context => `Odsłony: ${formatNumber(context.parsed.x)}`
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: '#edf1ef' },
          ticks: { color: '#647780', precision: 0 }
        },
        y: {
          grid: { display: false },
          ticks: { color: '#172d35' }
        }
      }
    }
  };
}

function replaceChart(name, canvas, config, ChartConstructor = Chart) {
  if (chartInstances[name]) chartInstances[name].destroy();
  chartInstances[name] = new ChartConstructor(canvas, config);
  return chartInstances[name];
}

function destroyCharts() {
  Object.keys(chartInstances).forEach(name => {
    chartInstances[name].destroy();
    delete chartInstances[name];
  });
}

function destroyChart(name) {
  if (!chartInstances[name]) return;
  chartInstances[name].destroy();
  delete chartInstances[name];
}

async function loadOverviewAnalytics(filters, request = authRequest, signal) {
  const query = buildDateQuery(filters.dateFrom, filters.dateTo);
  const endpoints = ['summary', 'sessions', 'activity', 'events', 'pages'];
  const [summary, sessions, activity, events, pages] = await Promise.all(
    endpoints.map(endpoint => request(`/api/analytics/${endpoint}${query}`, { signal }))
  );
  return { summary, sessions, activity, events, pages };
}

async function loadSessionAnalytics(filters, request = authRequest, signal) {
  const query = buildDateQuery(filters.dateFrom, filters.dateTo);
  return request(`/api/analytics/sessions${query}`, { signal });
}

async function authRequest(path, options = {}) {
  const controller = new AbortController();
  const externalSignal = options.signal;
  const abortFromExternal = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    externalSignal.addEventListener('abort', abortFromExternal);
  }
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
    if (externalSignal) externalSignal.removeEventListener('abort', abortFromExternal);
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

function renderKpis(summary, sessions) {
  const values = [
    ['Zdarzenia', summary.total_events],
    ['Sesje', summary.total_sessions],
    ['Odsłony stron', summary.page_views],
    ['Kliknięcia', summary.clicks],
    ['Wyświetlenia produktów', summary.product_views],
    ['Dodania do koszyka', summary.add_to_cart]
  ];
  const grid = document.querySelector('#kpi-grid');
  grid.replaceChildren();
  values.forEach(([label, value], index) => {
    const card = document.createElement('article');
    card.className = 'kpi-card';
    const number = document.createElement('span');
    number.className = 'kpi-number';
    number.textContent = formatNumber(value);
    const title = document.createElement('h3');
    title.textContent = label;
    const note = document.createElement('p');
    note.textContent = index === 1 ? 'Zarejestrowane sesje, nie osoby' : 'W wybranym okresie';
    card.append(number, title, note);
    grid.append(card);
  });

  const sessionNote = document.createElement('p');
  sessionNote.className = 'session-summary';
  sessionNote.textContent = `Średnio ${formatNumber(sessions.average_events_per_session)} zdarzeń na sesję · średni czas zarejestrowanej aktywności: ${formatNumber(sessions.average_activity_duration_seconds)} s`;
  grid.append(sessionNote);
}

function renderSessionAnalytics(data) {
  const grid = document.querySelector('#sessions-kpi-grid');
  grid.replaceChildren();
  buildSessionMetrics(data).forEach(([label, value, note]) => {
    const card = document.createElement('article');
    card.className = 'session-kpi-card';
    const number = document.createElement('span');
    number.className = 'session-kpi-number';
    number.textContent = value;
    const title = document.createElement('h3');
    title.textContent = label;
    const description = document.createElement('p');
    description.textContent = note;
    card.append(number, title, description);
    grid.append(card);
  });

  const sessionCount = Math.max(0, Number(data.session_count) || 0);
  const singleCount = Math.max(0, Number(data.single_event_session_count) || 0);
  const share = calculateSingleEventShare(sessionCount, singleCount);
  document.querySelector('#single-session-share').textContent = `${numberFormatter.format(share)}%`;
  document.querySelector('#single-session-bar').style.width = `${share}%`;
  document.querySelector('#single-session-detail').textContent = `${formatNumber(singleCount)} z ${formatNumber(sessionCount)} sesji`;
}

function renderActivity(rows) {
  const summary = document.querySelector('#activity-summary');
  const total = rows.reduce((sum, row) => sum + (Number(row.event_count) || 0), 0);
  document.querySelector('#activity-total').textContent = `${formatNumber(total)} zdarzeń`;
  summary.textContent = rows.map(row => `${row.date}: ${formatNumber(row.event_count)}`).join('; ');
  replaceChart(
    'activity',
    document.querySelector('#activity-chart'),
    buildActivityChartConfig(rows)
  );
}

function renderEventTypes(rows) {
  document.querySelector('#events-summary').textContent = rows
    .map(row => `${eventLabels[row.event_type] || row.event_type}: ${formatNumber(row.event_count)}`)
    .join('; ');
  replaceChart(
    'events',
    document.querySelector('#events-chart'),
    buildEventsChartConfig(rows)
  );
}

function renderPages(rows) {
  const ranking = document.querySelector('#pages-ranking');
  const normalizedRows = aggregatePageViews(rows).slice(0, 6);
  const chartContainer = document.querySelector('#pages-chart-container');
  const emptyMessage = document.querySelector('#pages-empty');
  ranking.replaceChildren();
  normalizedRows.forEach((row, index) => {
    const item = document.createElement('li');
    const position = document.createElement('span');
    position.className = 'ranking-position';
    position.textContent = String(index + 1).padStart(2, '0');
    const page = document.createElement('span');
    page.className = 'ranking-page';
    page.textContent = row.label;
    const value = document.createElement('strong');
    value.textContent = formatNumber(row.view_count);
    const suffix = document.createElement('small');
    suffix.textContent = ' odsłon';
    value.append(suffix);
    item.append(position, page, value);
    ranking.append(item);
  });
  if (!normalizedRows.length) {
    destroyChart('pages');
    chartContainer.hidden = true;
    emptyMessage.hidden = false;
    return;
  }
  chartContainer.hidden = false;
  emptyMessage.hidden = true;
  replaceChart(
    'pages',
    document.querySelector('#pages-chart'),
    buildPagesChartConfig(rows)
  );
}

function setupDashboard() {
  const gate = document.querySelector('#session-gate');
  const shell = document.querySelector('#dashboard-shell');
  const retry = document.querySelector('#session-retry');
  const message = document.querySelector('#session-message');
  const spinner = document.querySelector('#session-spinner');
  const status = document.querySelector('#dashboard-status');
  const logout = document.querySelector('#logout-button');
  const overviewPanel = document.querySelector('#overview-panel');
  const sessionsPanel = document.querySelector('#sessions-panel');
  const placeholderPanel = document.querySelector('#section-panel');
  const filterForm = document.querySelector('#date-filter');
  const dateFrom = document.querySelector('#date-from');
  const dateTo = document.querySelector('#date-to');
  const filterError = document.querySelector('#filter-error');
  const overviewLoading = document.querySelector('#overview-loading');
  const overviewError = document.querySelector('#overview-error');
  const overviewEmpty = document.querySelector('#overview-empty');
  const overviewContent = document.querySelector('#overview-content');
  const sessionsFilterForm = document.querySelector('#sessions-date-filter');
  const sessionsDateFrom = document.querySelector('#sessions-date-from');
  const sessionsDateTo = document.querySelector('#sessions-date-to');
  const sessionsFilterError = document.querySelector('#sessions-filter-error');
  const sessionsLoading = document.querySelector('#sessions-loading');
  const sessionsError = document.querySelector('#sessions-error');
  const sessionsEmpty = document.querySelector('#sessions-empty');
  const sessionsContent = document.querySelector('#sessions-content');
  let checking = false;
  let authenticated = false;
  let overviewController = null;
  let overviewRequestId = 0;
  let sessionsController = null;
  let sessionsRequestId = 0;

  function showOverviewState(state) {
    overviewLoading.hidden = state !== 'loading';
    overviewError.hidden = state !== 'error';
    overviewEmpty.hidden = state !== 'empty';
    overviewContent.hidden = state !== 'content';
  }

  async function refreshOverview() {
    if (!authenticated || window.location.hash.slice(1) && window.location.hash !== '#overview') return;
    const validationError = validateDateRange(dateFrom.value, dateTo.value);
    filterError.hidden = !validationError;
    filterError.textContent = validationError;
    if (validationError) return;

    if (overviewController) overviewController.abort();
    overviewController = new AbortController();
    const requestId = ++overviewRequestId;
    showOverviewState('loading');
    filterForm.querySelectorAll('button').forEach(button => { button.disabled = true; });
    try {
      const data = await loadOverviewAnalytics(
        { dateFrom: dateFrom.value, dateTo: dateTo.value },
        authRequest,
        overviewController.signal
      );
      if (requestId !== overviewRequestId) return;
      if (!data.summary.total_events) {
        destroyCharts();
        showOverviewState('empty');
        return;
      }
      showOverviewState('content');
      renderKpis(data.summary, data.sessions);
      renderActivity(data.activity);
      renderEventTypes(data.events);
      renderPages(data.pages);
    } catch (error) {
      if (requestId !== overviewRequestId || error.name === 'AbortError') return;
      if (error.status === 401) {
        authenticated = false;
        shell.hidden = true;
        goToLogin();
        return;
      }
      showOverviewState('error');
    } finally {
      if (requestId === overviewRequestId) {
        filterForm.querySelectorAll('button').forEach(button => { button.disabled = false; });
      }
    }
  }

  function showSessionsState(state) {
    sessionsLoading.hidden = state !== 'loading';
    sessionsError.hidden = state !== 'error';
    sessionsEmpty.hidden = state !== 'empty';
    sessionsContent.hidden = state !== 'content';
  }

  async function refreshSessions() {
    if (!authenticated || window.location.hash !== '#sessions') return;
    const validationError = validateDateRange(sessionsDateFrom.value, sessionsDateTo.value);
    sessionsFilterError.hidden = !validationError;
    sessionsFilterError.textContent = validationError;
    if (validationError) return;

    if (sessionsController) sessionsController.abort();
    sessionsController = new AbortController();
    const requestId = ++sessionsRequestId;
    showSessionsState('loading');
    sessionsFilterForm.querySelectorAll('button').forEach(button => { button.disabled = true; });
    try {
      const data = await loadSessionAnalytics(
        { dateFrom: sessionsDateFrom.value, dateTo: sessionsDateTo.value },
        authRequest,
        sessionsController.signal
      );
      if (requestId !== sessionsRequestId) return;
      if (!hasSessionData(data)) {
        showSessionsState('empty');
        return;
      }
      renderSessionAnalytics(data);
      showSessionsState('content');
    } catch (error) {
      if (requestId !== sessionsRequestId || error.name === 'AbortError') return;
      if (error.status === 401) {
        authenticated = false;
        shell.hidden = true;
        goToLogin();
        return;
      }
      showSessionsState('error');
    } finally {
      if (requestId === sessionsRequestId) {
        sessionsFilterForm.querySelectorAll('button').forEach(button => { button.disabled = false; });
      }
    }
  }

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
    overviewPanel.hidden = key !== 'overview';
    sessionsPanel.hidden = key !== 'sessions';
    placeholderPanel.hidden = key === 'overview' || key === 'sessions';
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
    if (key === 'overview' && authenticated) refreshOverview();
    if (key === 'sessions' && authenticated) refreshSessions();
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
      const needsInitialRender = needsDashboardRender(authenticated, shell.hidden);
      authenticated = true;
      gate.hidden = true;
      shell.hidden = false;
      if (needsInitialRender) showSection();
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
  filterForm.addEventListener('submit', event => {
    event.preventDefault();
    refreshOverview();
  });
  document.querySelector('#clear-filter').addEventListener('click', () => {
    dateFrom.value = '';
    dateTo.value = '';
    filterError.hidden = true;
    refreshOverview();
  });
  document.querySelector('#overview-retry').addEventListener('click', refreshOverview);
  sessionsFilterForm.addEventListener('submit', event => {
    event.preventDefault();
    refreshSessions();
  });
  document.querySelector('#sessions-clear-filter').addEventListener('click', () => {
    sessionsDateFrom.value = '';
    sessionsDateTo.value = '';
    sessionsFilterError.hidden = true;
    refreshSessions();
  });
  document.querySelector('#sessions-retry').addEventListener('click', refreshSessions);
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

if (typeof document !== 'undefined') {
  if (document.body.dataset.page === 'login') setupLogin();
  if (document.body.dataset.page === 'dashboard') setupDashboard();
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    aggregatePageViews,
    buildActivityChartConfig,
    buildDateQuery,
    buildEventsChartConfig,
    buildPagesChartConfig,
    buildSessionMetrics,
    calculateSingleEventShare,
    chartInstances,
    destroyChart,
    destroyCharts,
    formatNumber,
    formatDuration,
    hasSessionData,
    loadOverviewAnalytics,
    loadSessionAnalytics,
    needsDashboardRender,
    normalizeDemoShopPage,
    replaceChart,
    validateDateRange
  };
}
