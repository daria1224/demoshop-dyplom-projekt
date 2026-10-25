# Specyfikacja techniczna systemu DemoShop

## 1. Cel systemu

DemoShop jest demonstracyjnym systemem przygotowanym na potrzeby pracy dyplomowej „Projekt i implementacja systemu analizy aktywności użytkowników strony internetowej z wykorzystaniem technologii chmurowych”.

System ma umożliwiać rejestrowanie aktywności powiązanej z pseudonimową sesją, przesyłanie zdarzeń do API, ich walidację i zapis w PostgreSQL oraz udostępnianie podstawowych agregacji analitycznych. Docelowo agregacje zostaną zaprezentowane w chronionym panelu właściciela.

## 2. Zakres i wymagania

### Zakres istniejący

- demonstracyjna strona sklepu bez płatności i kont użytkowników;
- rejestrowanie wybranych zdarzeń interfejsu;
- pseudonimowa sesja przeglądarki;
- API odbierające i walidujące zdarzenia;
- zapis w relacyjnej bazie danych;
- agregacje zdarzeń, produktów, aktywności dziennej i odsłon stron;
- opcjonalne filtry dat dla aktywności i popularności stron.

### Funkcjonalności planowane w ramach pracy dyplomowej

- Dashboard analityczny;
- autoryzacja właściciela;
- rozbudowana analityka, filtry i wizualizacje;
- wdrożenie systemu w środowisku chmurowym.

### Funkcjonalności poza zakresem projektu

- rzeczywista sprzedaż i realizacja zamówień;
- płatności;
- konta klientów i identyfikacja konkretnych osób;
- analiza aktywności obejmująca wiele niezależnych witryn.

## 3. Moduły systemu

### 3.1. DemoShop

Statyczny frontend HTML, CSS i JavaScript udostępnia sześć podstron: główną, produkty, szczegóły produktu, koszyk, o nas i kontakt. Dane produktów znajdują się w `js/products.js`. `js/main.js` odpowiada za renderowanie produktów, obsługę koszyka, sesję i rejestrowanie zdarzeń.

### 3.2. Mechanizm zdarzeń

Funkcja `trackEvent()` buduje zdarzenie, zapisuje je w konsoli i wysyła metodą `POST` do `/api/events`. Nieudane połączenie albo odpowiedź HTTP 4xx/5xx jest raportowana w konsoli i nie blokuje działania sklepu. Zdarzenia nie są automatycznie ponawiane.

### 3.3. FastAPI

`backend/main.py` definiuje aplikację, model Pydantic oraz endpointy. Podstawowe pola zdarzenia są wymagane, a dodatkowe pola są akceptowane jako metadane. Znacznik czasu musi zawierać strefę czasową i jest normalizowany do UTC.

### 3.4. PostgreSQL Neon

`backend/database.py` odczytuje `DATABASE_URL` ze zmiennych środowiskowych, używa psycopg i wykonuje zapytania parametryzowane. Operacje zapisu zdarzenia odbywają się w jednej transakcji. Definicje tabel znajdują się w `backend/schema.sql`.

### 3.5. Planowany Dashboard

Dashboard nie istnieje w aktualnej wersji. Ma być osobnym, chronionym interfejsem prezentującym dane z `/api/analytics/*`. Przed publicznym udostępnieniem wszystkie endpointy analityczne muszą wymagać autoryzacji właściciela.

## 4. Przepływ danych

```text
działanie użytkownika
  → listener w js/main.js
  → trackEvent()
  → console.log()
  → POST /api/events
  → walidacja Pydantic
  → save_event()
  → sessions / pages / event_types / events
  → zapytania agregujące
  → GET /api/analytics/*
  → planowany Dashboard
```

## 5. Model zdarzenia

Każde zdarzenie zawiera pola podstawowe:

| Pole | Typ | Znaczenie |
|---|---|---|
| `session_token` | tekst | losowy, pseudonimowy identyfikator sesji |
| `event_type` | tekst | nazwa typu zdarzenia |
| `page` | tekst | ścieżka aktualnej strony |
| `timestamp` | ISO 8601 | czas zdarzenia ze strefą, normalizowany do UTC |

Dodatkowe pola trafiają do `events.metadata` jako JSONB.

| Typ zdarzenia | Moment rejestracji | Typowe metadane |
|---|---|---|
| `page_view` | otwarcie podstrony | `title` |
| `click` | istotne kliknięcie | `element`, `destination`, `product_id`, `product_name`, `open` |
| `view_item` | otwarcie szczegółów produktu | `product_id`, `product_name` |
| `add_to_cart` | dodanie produktu do koszyka | `product_id`, `product_name`, `cart_count` |
| `form_submit` | poprawne zatwierdzenie demonstracyjnego formularza po walidacji klienta | `form` |

Zdarzenie `form_submit` nie oznacza wysłania wiadomości do odbiorcy ani zapisania jej treści. Formularz jest wyłącznie demonstracyjny, a treść pól, imię i adres e-mail nie są przesyłane jako dane analityczne.

## 6. Model sesji

- token powstaje z `crypto.randomUUID()`, a w starszym środowisku z mechanizmu awaryjnego;
- token i czas ostatniej aktywności są przechowywane w Local Storage;
- każde rejestrowane zdarzenie aktualizuje czas ostatniej aktywności;
- kolejne zdarzenie po co najmniej 30 minutach bez aktywności otrzymuje nowy token;
- przejścia między podstronami oraz ponowne otwarcie przeglądarki przed upływem limitu zachowują token;
- usunięcie Local Storage rozpoczyna nową sesję;
- token jest losowym identyfikatorem pseudonimowym, nie reprezentuje uwierzytelnionego użytkownika i sam nie identyfikuje konkretnej osoby;
- pseudonimizacja tokenu nie stanowi gwarancji pełnej anonimowości użytkownika.

Backend wyznacza granice aktywności sesji jako najwcześniejszy `started_at` i najpóźniejszy `last_seen_at`. Użycie `LEAST` i `GREATEST` zabezpiecza te wartości przed zdarzeniami przychodzącymi poza kolejnością.

## 7. Model danych

### `sessions`

- `id BIGSERIAL PRIMARY KEY`;
- `session_id TEXT NOT NULL UNIQUE`;
- `started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`;
- `last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`;
- `user_agent TEXT`, opcjonalny.

### `pages`

- `id BIGSERIAL PRIMARY KEY`;
- `url TEXT NOT NULL UNIQUE`;
- `title TEXT NOT NULL`.

### `event_types`

- `id BIGSERIAL PRIMARY KEY`;
- `name TEXT NOT NULL UNIQUE`;
- `description TEXT`, opcjonalny.

### `events`

- `id BIGSERIAL PRIMARY KEY`;
- `session_id BIGINT NOT NULL`, klucz obcy do `sessions.id`;
- `page_id BIGINT NOT NULL`, klucz obcy do `pages.id`;
- `event_type_id BIGINT NOT NULL`, klucz obcy do `event_types.id`;
- `element_name TEXT`, opcjonalny;
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`;
- `created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`.

Jedna sesja, strona i nazwa typu mogą być powiązane z wieloma zdarzeniami.

## 8. Endpointy

| Metoda | Ścieżka | Stan | Wynik |
|---|---|---|---|
| `GET` | `/` | istnieje | komunikat kontrolny API |
| `GET` | `/api/db-test` | istnieje | informacja o połączeniu z bazą |
| `POST` | `/api/events` | istnieje | walidacja i zapis zdarzenia |
| `GET` | `/api/analytics/summary` | istnieje | podstawowe liczniki |
| `GET` | `/api/analytics/events` | istnieje | liczba zdarzeń według typu |
| `GET` | `/api/analytics/products` | istnieje | widoki i dodania produktów |
| `GET` | `/api/analytics/activity` | istnieje | liczba wszystkich zdarzeń według dnia UTC |
| `GET` | `/api/analytics/pages` | istnieje | liczba zdarzeń `page_view` według strony |
| `GET` | `/api/analytics/sessions` | istnieje | zbiorcze statystyki sesji i czasu aktywności |
| `GET` | `/api/analytics/clicks` | istnieje | ranking kliknięć według elementu, strony i celu |

`activity` i `pages` przyjmują opcjonalne `date_from` i `date_to` w formacie `YYYY-MM-DD`. Granice są włączne i odnoszą się do UTC. Odwrócony zakres jest odrzucany kodem 422. `activity` uzupełnia dni z wartością zero tylko wtedy, gdy określono obie granice.

`sessions` i `clicks` przyjmują takie same opcjonalne, włączne granice dni UTC. W `sessions` zakres wybiera zdarzenia, a nie całe historyczne sesje: uwzględniane są sesje z co najmniej jednym zdarzeniem w okresie, natomiast ich liczba zdarzeń i czas aktywności są obliczane wyłącznie z danych należących do okresu.

## 9. Zasady obliczania wskaźników

- `total_events`: liczba rekordów `events`;
- `total_sessions`: liczba różnych kluczy `events.session_id`, nie liczba użytkowników;
- `page_views`: liczba zdarzeń `page_view`;
- `clicks`: liczba zdarzeń `click`;
- `product_views`: liczba zdarzeń `view_item`;
- `add_to_cart`: liczba zdarzeń `add_to_cart`;
- zestawienie typów: liczba zdarzeń pogrupowana według `event_types.name`;
- popularność produktu: liczby `view_item` i `add_to_cart` według pól produktu w JSONB;
- aktywność dzienna: wszystkie zdarzenia pogrupowane według dnia UTC;
- popularność stron: wyłącznie `page_view` pogrupowane według `pages.url`;
- ranking kliknięć: wyłącznie zdarzenia `click`, pogrupowane według elementu, strony i opcjonalnego celu.

### 9.1. Analityka sesji

Endpoint `/api/analytics/sessions` najpierw agreguje zdarzenia osobno dla każdej sesji, a dopiero później oblicza wartości zbiorcze. Zapobiega to mnożeniu rekordów podczas łączenia tabel.

- liczba sesji oznacza liczbę różnych sesji, w których zarejestrowano co najmniej jedno zdarzenie; nie jest to liczba unikalnych użytkowników;
- czas zarejestrowanej aktywności jednej sesji to różnica w sekundach między `MAX(events.created_at)` i `MIN(events.created_at)`;
- sesja zawierająca jedno zdarzenie ma czas aktywności równy `0` sekund;
- średni czas aktywności to średnia arytmetyczna czasów wszystkich uwzględnionych sesji, łącznie z sesjami o czasie `0`;
- mediana czasu aktywności jest obliczana przez PostgreSQL jako `PERCENTILE_CONT(0.5)` dla czasów sesji;
- liczba sesji z jednym zdarzeniem obejmuje sesje, dla których `COUNT(events.id) = 1`;
- średnia liczba zdarzeń na sesję to średnia z liczby zdarzeń obliczonej osobno dla każdej uwzględnionej sesji.

Przy aktywnych filtrach dat do obliczeń trafiają wyłącznie zdarzenia z włącznego zakresu dni UTC. Sesja może więc mieć wcześniejsze lub późniejsze zdarzenia poza zakresem, ale nie wpływają one na wynik. Granice aktywności są wyznaczane z tabeli `events`, a nie z historycznych wartości `sessions.started_at` i `sessions.last_seen_at`.

Czas aktywności jest przybliżeniem odstępu między pierwszym i ostatnim zarejestrowanym zdarzeniem. Nie określa dokładnego czasu obecności użytkownika na stronie, nie obejmuje okresu po ostatnim zdarzeniu i zależy od poprawności czasu przesłanego przez klienta.

### 9.2. Analityka kliknięć

Endpoint `/api/analytics/clicks` uwzględnia wyłącznie zdarzenia typu `click`. Każda grupa jest określona przez:

- `element`: kolejno `events.element_name`, `metadata.element` albo wartość `unknown`;
- `page`: adres z `pages.url`;
- `target`: kolejno `metadata.product_id`, `metadata.destination` albo `null`.

Liczba kliknięć jest obliczana osobno dla każdej kombinacji elementu, strony i celu. Wyniki są sortowane malejąco według liczby kliknięć, a przy remisie stabilnie według elementu, strony i celu. Brakujące metadane nie powodują pominięcia zdarzenia. Ranking nie zawiera danych osobowych, ale jego interpretacja zależy od spójności identyfikatorów elementów przekazywanych przez frontend.

## 10. Planowane analizy i wizualizacje

- karty podstawowych statystyk;
- wykres aktywności dziennej;
- wykres udziału typów zdarzeń;
- ranking podstron i produktów;
- tabela ostatnich zdarzeń;
- wizualizacja czasu aktywności sesji i jego rozkładu;
- współczynnik przejścia od wyświetlenia produktu do dodania do koszyka;
- filtry według dat, strony, typu zdarzenia i produktu.

## 11. Autoryzacja właściciela

Aktualne endpointy analityczne nie wymagają logowania. Przed publicznym wdrożeniem system musi:

- uwierzytelniać właściciela panelu;
- sprawdzać uprawnienia przy każdym `/api/analytics/*`;
- nie przechowywać sekretów uwierzytelniających w repozytorium;
- używać bezpiecznych ciasteczek lub tokenów odpowiednich dla wybranej architektury;
- ograniczać dostęp do danych i operacji administracyjnych.

Wybór konkretnej metody autoryzacji pozostaje elementem planowanego rozwoju.

## 12. Bezpieczeństwo i ochrona danych

- dane dostępowe do bazy znajdują się poza kodem, w `DATABASE_URL`;
- `.env` jest ignorowany przez Git;
- zapytania korzystają z parametrów zamiast interpolowania danych użytkownika;
- zdarzenia są walidowane przez Pydantic;
- identyfikator sesji jest pseudonimowy, nie zawiera danych bezpośrednio identyfikujących osobę, ale nie gwarantuje pełnej anonimowości;
- formularz kontaktowy nie przesyła treści wiadomości ani danych kontaktowych do analityki;
- błędy API nie ujawniają adresu połączenia z bazą;
- czas jest zapisywany jako `TIMESTAMPTZ` i normalizowany do UTC.

Przed wdrożeniem wymagane są dodatkowo autoryzacja, ograniczenie CORS do znanych adresów, HTTPS, limity żądań, monitoring błędów i przegląd zasad retencji danych.

## 13. Możliwość wdrożenia chmurowego

Backend może zostać później uruchomiony na platformie obsługującej Python i zmienne środowiskowe, a frontend na hostingu statycznym. Adres API frontendu, CORS, sekrety, HTTPS i autoryzacja będą wymagały konfiguracji właściwej dla wybranego środowiska.

Repozytorium nie zawiera obecnie Dockerfile, Terraform ani konfiguracji konkretnej platformy. Projekt nie został jeszcze opisany jako wdrożony produkcyjnie.
