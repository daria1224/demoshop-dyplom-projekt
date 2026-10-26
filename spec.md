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
- statystyki sesji, ranking kliknięć, historia ostatnich zdarzeń i lejek produktów;
- opcjonalne filtry dat dla zestawień analitycznych;
- uwierzytelnianie jednego właściciela i ochrona API analitycznego;
- strona logowania i responsywny szkielet Dashboardu, z nawigacją pięciu sekcji.

### Funkcjonalności planowane w ramach pracy dyplomowej

- wykresy, tabele i filtry danych w Dashboardzie;
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

### 3.5. Dashboard — etap 1

FastAPI obsługuje `/dashboard/login`, `/dashboard` oraz zasoby z `dashboard/assets` pod `/dashboard/assets`. Ścieżki do plików są wyznaczane względem projektu, niezależnie od bieżącego katalogu procesu. Panel wykorzystuje HTML, CSS i zwykły JavaScript, bez osobnego serwera frontendowego i procesu kompilacji.

Dokumenty HTML mają `Cache-Control: no-store` i są publicznym szkieletem bez danych analitycznych. Cookie pozostaje ograniczone do `Path=/api`. Skrypt sprawdza `/api/auth/status` przed pokazaniem panelu. Brak aktywnej sesji przekierowuje do formularza, a aktywna sesja na stronie logowania przekierowuje do panelu. Kontrola następuje także przy zmianie sekcji, powrocie do karty i co 60 sekund w widocznej karcie. Po wykryciu wygaśnięcia następuje przekierowanie do logowania; dane API pozostają chronione niezależnie od skryptu.

Formularz wysyła JSON do `/api/auth/login`, obsługuje Enter, oczekiwanie i komunikaty błędów. Wylogowanie wywołuje `/api/auth/logout`; niepowodzenie nie jest przedstawiane jako sukces. Żądania używają `credentials: same-origin`, względnych adresów API i limitu oczekiwania 10 sekund. Hasło nie jest logowane ani zapisywane w pamięci przeglądarki; pole jest czyszczone po próbie logowania.

Nawigacja oparta na fragmentach URL przełącza Przegląd, Sesje, Strony i interakcje, Produkty i Zdarzenia, aktualizując nagłówek oraz aktywną pozycję menu. Sekcje zawierają wyłącznie opisy planowanych zestawień. Etap 1 nie pobiera jeszcze danych z `/api/analytics/*`, nie prezentuje statystyk, wykresów ani tabel. Nie uruchamia też mechanizmu zdarzeń publicznego sklepu.

### 3.6. Uwierzytelnianie właściciela

`backend/auth.py` realizuje uwierzytelnianie jednego właściciela bez tabel kont. Nazwa właściciela, hash Argon2 hasła oraz sekret podpisu znajdują się w zmiennych środowiskowych. Po poprawnym logowaniu backend ustawia podpisane, czasowe ciasteczko `HttpOnly`. Wspólna zależność routera chroni wszystkie `/api/analytics/*`, a osobna zależność chroni `/api/db-test`.

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
  → planowana prezentacja w istniejącym szkielecie Dashboardu
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
| `GET` | `/dashboard/login` | istnieje | publiczny formularz logowania |
| `GET` | `/dashboard` | istnieje | szkielet interfejsu właściciela bez danych analitycznych |
| `GET` | `/api/db-test` | istnieje | informacja o połączeniu z bazą |
| `POST` | `/api/events` | istnieje | walidacja i zapis zdarzenia |
| `POST` | `/api/auth/login` | istnieje | weryfikacja właściciela i utworzenie sesji |
| `POST` | `/api/auth/logout` | istnieje | usunięcie ciasteczka sesyjnego |
| `GET` | `/api/auth/status` | istnieje | stan uwierzytelnienia właściciela |
| `GET` | `/api/analytics/summary` | istnieje | podstawowe liczniki |
| `GET` | `/api/analytics/events` | istnieje | liczba zdarzeń według typu |
| `GET` | `/api/analytics/products` | istnieje | widoki i dodania produktów |
| `GET` | `/api/analytics/activity` | istnieje | liczba wszystkich zdarzeń według dnia UTC |
| `GET` | `/api/analytics/pages` | istnieje | liczba zdarzeń `page_view` według strony |
| `GET` | `/api/analytics/sessions` | istnieje | zbiorcze statystyki sesji i czasu aktywności |
| `GET` | `/api/analytics/clicks` | istnieje | ranking kliknięć według elementu, strony i celu |
| `GET` | `/api/analytics/recent-events` | istnieje | najnowsze zdarzenia z kontrolowanym zestawem pól |
| `GET` | `/api/analytics/funnel` | istnieje | lejek wyświetlenie produktu → dodanie do koszyka |

`activity` i `pages` przyjmują opcjonalne `date_from` i `date_to` w formacie `YYYY-MM-DD`. Granice są włączne i odnoszą się do UTC. Odwrócony zakres jest odrzucany kodem 422. `activity` uzupełnia dni z wartością zero tylko wtedy, gdy określono obie granice.

`sessions` i `clicks` przyjmują takie same opcjonalne, włączne granice dni UTC. W `sessions` zakres wybiera zdarzenia, a nie całe historyczne sesje: uwzględniane są sesje z co najmniej jednym zdarzeniem w okresie, natomiast ich liczba zdarzeń i czas aktywności są obliczane wyłącznie z danych należących do okresu.

`recent-events` i `funnel` przyjmują opcjonalne `date_from` i `date_to` o tej samej semantyce. `recent-events` obsługuje dodatkowo całkowity parametr `limit` od `1` do `100`, domyślnie `20`. Nieprawidłowy limit, format daty albo zakres z `date_from` późniejszym niż `date_to` jest odrzucany kodem 422.

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

### 9.3. Historia ostatnich zdarzeń

Endpoint `/api/analytics/recent-events` łączy `events` z `pages` i `event_types`. Rekordy są sortowane malejąco według `events.created_at`, a przy identycznym czasie malejąco według `events.id`. Czas jest zwracany w formacie ISO 8601 UTC z oznaczeniem `Z`.

Odpowiedź zawiera wyłącznie bezpieczną listę pól potrzebnych do przyszłej tabeli analitycznej:

- `event_id` — techniczny identyfikator zdarzenia;
- `timestamp` — czas zdarzenia w UTC;
- `event_type` — nazwa typu zdarzenia;
- `page` — ścieżka strony;
- `element` — opcjonalna nazwa elementu z `element_name` albo `metadata.element`;
- `product_id` i `product_name` — opcjonalne dane produktu.

Endpoint nie zwraca `session_token`, całego `metadata`, danych formularza ani innych dodatkowych wartości przesłanych przez klienta. Filtry dat obejmują włączne dni UTC. Pusty zakres danych zwraca pustą tablicę.

### 9.4. Lejek interakcji z produktami

Endpoint `/api/analytics/funnel` wykorzystuje zdarzenia `view_item` i `add_to_cart`, które mają niepusty `metadata.product_id`. Jednostką analizy jest unikalna para `(session_id, product_id)`, a nie użytkownik ani pojedyncze zdarzenie.

- para wchodzi do pierwszego etapu, jeżeli ma co najmniej jedno `view_item`;
- para przechodzi do drugiego etapu, jeżeli po dowolnym jej `view_item` wystąpi `add_to_cart` tego samego produktu w tej samej sesji;
- wielokrotne odsłony i dodania nie zwiększają liczby tej samej pary;
- `add_to_cart` bez wcześniejszego `view_item` nie jest konwersją;
- wyświetlenie jednego produktu i dodanie innego nie jest konwersją.

Chronologia jest porównywana jako para `(events.created_at, events.id)`. Wcześniejszy czas ma pierwszeństwo, a przy identycznych znacznikach czasu zdarzenie z większym `id` jest uznawane za późniejsze. Reguła dla remisu jest deterministyczna, ale nie dowodzi rzeczywistej kolejności dwóch działań wykonanych w tej samej chwili.

Wynik globalny i wyniki produktów zawierają liczbę wyświetlonych par, liczbę par skonwertowanych oraz procent `converted_session_product_pairs / viewed_session_product_pairs * 100`, zaokrąglony do dwóch miejsc. Dla zerowego mianownika zwracane jest `0.0`.

Jeżeli zastosowano daty, zarówno `view_item`, jak i późniejsze `add_to_cart` muszą mieścić się we włącznym zakresie dni UTC. Konwersje przekraczające granicę filtra nie są uwzględniane, dlatego wynik ograniczonego okresu nie jest pełną historyczną konwersją sesji. Współczynnik opisuje przejście między dwoma zdarzeniami DemoShop; nie jest współczynnikiem rzeczywistych zakupów ani konwersją unikalnych użytkowników.

## 10. Planowane analizy i wizualizacje

- karty podstawowych statystyk;
- wykres aktywności dziennej;
- wykres udziału typów zdarzeń;
- ranking podstron i produktów;
- tabela ostatnich zdarzeń na podstawie istniejącego endpointu;
- wizualizacja czasu aktywności sesji i jego rozkładu;
- wizualizacja istniejącego współczynnika przejścia od wyświetlenia produktu do dodania do koszyka;
- filtry według dat, strony, typu zdarzenia i produktu.

## 11. Uwierzytelnianie właściciela

- `OWNER_USERNAME` określa nazwę jedynego właściciela;
- `OWNER_PASSWORD_HASH` zawiera hash Argon2, nigdy hasło jawne;
- `OWNER_SESSION_SECRET` jest niezależnym, losowym sekretem podpisu o długości co najmniej 32 znaków;
- `OWNER_SESSION_TTL_SECONDS` określa ważność od 5 minut do 24 godzin, domyślnie 30 minut;
- `AUTH_COOKIE_SECURE` domyślnie włącza flagę `Secure`; wartość `false` służy wyłącznie lokalnemu HTTP;
- `CORS_ALLOWED_ORIGINS` zawiera jawne originy publicznego frontendu i nie dopuszcza `*`;
- opcjonalne `AUTH_ALLOWED_ORIGINS` osobno dopuszcza zaufany origin interfejsu właściciela, gdy nie działa on same-origin.

Hasło jest weryfikowane przez `argon2-cffi`. Login jest porównywany przez `secrets.compare_digest()` na bajtach UTF-8, zarówno przy logowaniu, jak i przy sprawdzaniu właściciela sesji. Obsługuje to również polskie znaki. Po zalogowaniu `itsdangerous` podpisuje dane sesji i dodaje znacznik czasu. Ciasteczko ma `HttpOnly`, `SameSite=Strict`, ścieżkę `/api`, ograniczony `Max-Age` oraz w HTTPS flagę `Secure`. Ważność jest liczona od logowania i nie jest automatycznie przedłużana. Logowanie i wylogowanie wymagają dozwolonego nagłówka `Origin`; domyślnie dopuszczony jest origin bieżącego API. Publiczne originy CORS nie są automatycznie dopuszczane do logowania.

`POST /api/auth/login` przyjmuje JSON z polami `username` i `password`. Błędy danych uwierzytelniających zwracają 401 ze wspólnym komunikatem. Błędy walidacji tej trasy, w tym niepoprawny typ, struktura lub JSON, zwracają 422 ze stałym komunikatem bez pola `input`, treści żądania ani hasła. Obsługa walidacji pozostałych endpointów pozostaje standardowa. Kod aplikacji nie loguje danych logowania.

Limiter atomowo rezerwuje próbę pod blokadą w jednym procesie. Suma nieudanych prób zakończonych w ostatnich 15 minutach i trwających weryfikacji z danego adresu klienta nie może przekroczyć pięciu. Kolejna próba otrzymuje 429 z `Retry-After`. Kosztowna weryfikacja Argon2 odbywa się poza blokadą. Rezerwacja jest zwalniana w `finally`: niepoprawne dane pozostawiają wpis błędu z czasem zakończenia, sukces usuwa wcześniejsze błędy, a błąd konfiguracji zwalnia miejsce bez naliczania nieudanej próby. Sukces nie usuwa rezerwacji innych trwających żądań. Wygasłe wpisy wszystkich adresów są usuwane podczas rezerwowania kolejnej próby; nie działa osobny proces sprzątający.

Sesja jest bezstanowa: serwer weryfikuje podpis, wiek i właściciela bez zapisywania tokenu w bazie. Wylogowanie usuwa ciasteczko z bieżącej przeglądarki, lecz przechwyconej kopii poprawnie podpisanego tokenu nie można centralnie unieważnić przed upływem czasu ważności. Zmiana `OWNER_SESSION_SECRET` unieważnia wszystkie aktywne sesje. Limiter prób jest przechowywany w pamięci procesu, więc przy wielu instancjach wymagałby współdzielonego magazynu.

Brak poprawnej konfiguracji zwraca 503 i nie otwiera dostępu do analityki. Brak lub nieważna sesja zwraca 401. `POST /api/events` pozostaje publiczny, natomiast `/api/db-test` wymaga sesji właściciela.

`GET /api/auth/status` zwraca wyłącznie `authenticated`: brak, wygaśnięcie lub niepoprawność sesji, a także brak konfiguracji dają wartość `false`. Mechanizm właściciela jest niezależny od 30-minutowego limitu bezczynności pseudonimowych sesji sklepu. System nie zawiera rejestracji, ról, odzyskiwania haseł ani kont klientów.

Testy w `tests/test_auth.py` izolują konfigurację i zapis, nie odczytują `.env` oraz nie łączą się z Neon. Sprawdzają logowanie, błędy walidacji, Unicode, współbieżne rezerwacje, odpowiedzi 429, usuwanie wygasłych wpisów, zwalnianie rezerwacji po błędzie konfiguracji, cookie, wylogowanie i ochronę tras.

`tests/test_dashboard.py` sprawdza serwowanie HTML i zasobów, brak danych uwierzytelniających w HTML, zachowanie ścieżki cookie, logowanie i wylogowanie, wygaśnięcie sesji oraz dostępność istniejących dziewięciu tras analitycznych z atrapami zapytań. Testy nie zapisują danych w Neon.

## 12. Bezpieczeństwo i ochrona danych

- dane dostępowe do bazy znajdują się poza kodem, w `DATABASE_URL`;
- `.env` jest ignorowany przez Git;
- zapytania korzystają z parametrów zamiast interpolowania danych użytkownika;
- zdarzenia są walidowane przez Pydantic;
- identyfikator sesji jest pseudonimowy, nie zawiera danych bezpośrednio identyfikujących osobę, ale nie gwarantuje pełnej anonimowości;
- formularz kontaktowy nie przesyła treści wiadomości ani danych kontaktowych do analityki;
- błędy API nie ujawniają adresu połączenia z bazą;
- czas jest zapisywany jako `TIMESTAMPTZ` i normalizowany do UTC;
- odpowiedzi błędów logowania nie ujawniają, czy błędna była nazwa, czy hasło;
- operacje logowania i wylogowania sprawdzają `Origin`, a ciasteczko używa `SameSite=Strict`.

Przed wdrożeniem wymagane są dodatkowo HTTPS, ustawienie docelowych originów, trwały limiter odpowiedni dla liczby instancji, monitoring błędów i przegląd zasad retencji danych.

## 13. Możliwość wdrożenia chmurowego

Backend może zostać później uruchomiony na platformie obsługującej Python i zmienne środowiskowe, a frontend na hostingu statycznym. Adres API frontendu, CORS, sekrety i HTTPS będą wymagały konfiguracji właściwej dla wybranego środowiska.

Repozytorium nie zawiera obecnie Dockerfile, Terraform ani konfiguracji konkretnej platformy. Projekt nie został jeszcze opisany jako wdrożony produkcyjnie.
