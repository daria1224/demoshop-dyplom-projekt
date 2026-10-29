# DemoShop — system analizy aktywności użytkowników

DemoShop jest projektem dyplomowym realizowanym w ramach pracy:

> „Projekt i implementacja systemu analizy aktywności użytkowników strony internetowej z wykorzystaniem technologii chmurowych”.

Celem projektu jest zaprojektowanie i zaimplementowanie prostego systemu, który rejestruje aktywność powiązaną z pseudonimową sesją demonstracyjnej strony internetowej, zapisuje zdarzenia w PostgreSQL i udostępnia zagregowane dane przez API analityczne.

## DemoShop

DemoShop to fikcyjny, responsywny sklep internetowy zbudowany bez frameworków frontendowych. Serwis zawiera stronę główną, katalog produktów, szczegóły produktu, koszyk, informacje o sklepie i formularz kontaktowy. Nie realizuje płatności, kont użytkowników ani prawdziwych zamówień.

Strona jest źródłem rzeczywistych interakcji wykorzystywanych do demonstracji systemu analitycznego, takich jak odsłony stron, kliknięcia, wyświetlenia produktów, dodania do koszyka i poprawne zatwierdzenie demonstracyjnego formularza po walidacji w przeglądarce. Formularz nie wysyła rzeczywistej wiadomości.

## Architektura

```text
DemoShop (HTML, CSS, JavaScript)
        │
        │ POST /api/events
        ▼
FastAPI + Pydantic
        │
        │ zapytania parametryzowane
        ▼
PostgreSQL (Neon)
        │
        │ agregacje SQL
        ▼
GET /api/analytics/*
```

Frontend zapisuje zdarzenia również w konsoli przeglądarki, co ułatwia lokalne testowanie. Awaria API analitycznego nie blokuje zwykłego korzystania ze sklepu.

## Technologie

- HTML5, CSS3 i JavaScript;
- Chart.js 4.6.1 do wykresów Dashboardu;
- Local Storage;
- Python 3.13;
- FastAPI i Pydantic;
- Uvicorn;
- psycopg 3;
- Argon2 (`argon2-cffi`) do weryfikacji hasła właściciela;
- `itsdangerous` do podpisywania czasowych ciasteczek sesyjnych;
- PostgreSQL w usłudze Neon;
- SQL i typ `JSONB` dla dodatkowych danych zdarzeń.

## Struktura projektu

```text
demoshop/
├── backend/
│   ├── auth.py           # uwierzytelnianie właściciela i limiter logowania
│   ├── database.py       # połączenie z PostgreSQL i zapytania SQL
│   ├── main.py           # aplikacja FastAPI i endpointy
│   └── schema.sql        # definicje tabel bazy danych
├── css/
│   ├── cart.css          # style strony koszyka
│   └── style.css         # wspólne style serwisu
├── dashboard/
│   ├── assets/
│   │   ├── vendor/       # lokalny Chart.js 4.6.1 i licencja MIT
│   │   ├── dashboard.css # style panelu i logowania
│   │   └── dashboard.js  # sesja, dane, wykresy i przełączanie sekcji
│   ├── index.html       # publiczny szkielet panelu właściciela
│   └── login.html       # formularz logowania
├── js/
│   ├── main.js           # interakcje, koszyk i rejestrowanie zdarzeń
│   └── products.js       # demonstracyjny katalog produktów
├── tests/
│   ├── test_auth.py      # izolowane testy uwierzytelniania
│   └── test_dashboard.py # strony, zasoby i integracja sesji panelu
├── about.html
├── cart.html
├── contact.html
├── index.html
├── product.html
├── products.html
├── requirements.txt
├── spec.md
└── README.md
```

## Uruchomienie lokalne

### 1. Środowisko Python

W katalogu projektu utwórz i aktywuj środowisko wirtualne:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Konfiguracja bazy

Utwórz w katalogu głównym plik `.env`:

```dotenv
DATABASE_URL=<adres_połączenia_PostgreSQL>
OWNER_USERNAME=<nazwa_właściciela>
OWNER_PASSWORD_HASH=<hash_Argon2_hasła>
OWNER_SESSION_SECRET=<losowy_sekret_co_najmniej_32_znaki>
OWNER_SESSION_TTL_SECONDS=1800
AUTH_COOKIE_SECURE=false
```

Wstaw własny adres połączenia otrzymany od dostawcy PostgreSQL. Hash hasła można wygenerować lokalnie za pomocą `PasswordHasher` z biblioteki `argon2-cffi`; w konfiguracji zapisuje się wyłącznie wynik haszowania, nigdy jawne hasło. Sekret sesji powinien być losowy i niezależny od hasła. `AUTH_COOKIE_SECURE=false` jest dopuszczalne wyłącznie podczas pracy lokalnej przez HTTP — w środowisku HTTPS należy pozostawić wartość domyślną `true`. Opcjonalne `AUTH_ALLOWED_ORIGINS` jest potrzebne tylko dla zaufanego Dashboardu działającego w innym originie; zalecane jest obsługiwanie go przez ten sam serwer FastAPI. Plik `.env` jest ignorowany przez Git i nie powinien być publikowany.

Przykładowe lokalne polecenia generujące hash i losowy sekret:

```powershell
python -c "from getpass import getpass; from argon2 import PasswordHasher; print(PasswordHasher().hash(getpass('Hasło właściciela: ')))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Dla nowej bazy wykonaj polecenia z `backend/schema.sql`, na przykład w edytorze SQL Neon. Nie wykonuj ich ponownie na bazie, w której tabele już istnieją.

### 3. Backend

Uruchom FastAPI z katalogu głównego projektu:

```powershell
python -m uvicorn backend.main:app --reload
```

Jedna aplikacja będzie dostępna pod adresem `http://127.0.0.1:8000`. FastAPI udostępnia publiczny DemoShop, Dashboard i API w tym samym originie. Interaktywna dokumentacja API znajduje się pod `http://127.0.0.1:8000/docs`.

Publiczny sklep otwórz pod `http://127.0.0.1:8000/`, logowanie właściciela pod `http://127.0.0.1:8000/dashboard/login`, a panel pod `http://127.0.0.1:8000/dashboard`. Strony i ich zasoby obsługuje FastAPI; nie wymagają osobnego serwera frontendowego. W lokalnej konfiguracji HTTP potrzebne jest `AUTH_COOKIE_SECURE=false`. Dla HTTPS użyj `true`.

### 4. Publiczny DemoShop

Nie uruchamiaj osobnego serwera statycznego. Strony DemoShop korzystają ze względnego adresu `/api/events`, dlatego zdarzenia są wysyłane do tej samej aplikacji FastAPI i tego samego originu. Dostępne podstrony to:

- `/` oraz `/index.html` — strona główna;
- `/products.html` — produkty;
- `/product.html?id=<identyfikator>` — szczegóły produktu;
- `/cart.html` — koszyk;
- `/about.html` — o nas;
- `/contact.html` — kontakt.

## Endpointy API

| Metoda | Ścieżka | Działanie |
|---|---|---|
| `GET` | `/` i `/index.html` | Publiczna strona główna DemoShop |
| `GET` | `/products.html`, `/product.html`, `/cart.html`, `/about.html`, `/contact.html` | Publiczne podstrony DemoShop |
| `GET` | `/api/health` | Informacja o działaniu API |
| `GET` | `/dashboard/login` | Strona logowania właściciela |
| `GET` | `/dashboard` | Panel właściciela z pięcioma sekcjami nawigacji |
| `GET` | `/api/db-test` | Kontrola połączenia z PostgreSQL |
| `POST` | `/api/events` | Walidacja i zapis pojedynczego zdarzenia |
| `POST` | `/api/auth/login` | Logowanie właściciela i ustawienie ciasteczka sesyjnego |
| `POST` | `/api/auth/logout` | Wylogowanie właściciela i usunięcie ciasteczka |
| `GET` | `/api/auth/status` | Informacja o stanie uwierzytelnienia |
| `GET` | `/api/analytics/summary` | Podstawowe liczniki zdarzeń i sesji |
| `GET` | `/api/analytics/events` | Liczba zdarzeń według typu |
| `GET` | `/api/analytics/products` | Wyświetlenia produktów i dodania do koszyka |
| `GET` | `/api/analytics/activity` | Liczba wszystkich zdarzeń według dnia UTC |
| `GET` | `/api/analytics/pages` | Liczba odsłon stron na podstawie `page_view` |
| `GET` | `/api/analytics/sessions` | Liczba sesji oraz statystyki zarejestrowanej aktywności |
| `GET` | `/api/analytics/clicks` | Ranking klikanych elementów według strony i celu |
| `GET` | `/api/analytics/recent-events` | Historia najnowszych zdarzeń z bezpiecznym zestawem pól |
| `GET` | `/api/analytics/funnel` | Lejek wyświetlenie produktu → dodanie do koszyka |

Endpointy `/api/analytics/summary`, `/api/analytics/events`, `/api/analytics/activity` i `/api/analytics/pages` przyjmują opcjonalne parametry `date_from` i `date_to` w formacie `YYYY-MM-DD`. Granice są włączne i odnoszą się do dni w UTC. Pełny przedział w `/activity` zawiera także dni bez zdarzeń, z wartością `0`.

Endpointy `/api/analytics/sessions` i `/api/analytics/clicks` obsługują te same opcjonalne granice dni UTC. W analityce sesji filtr wybiera zdarzenia z okresu, a statystyki każdej sesji są liczone wyłącznie na podstawie zdarzeń znajdujących się w tym okresie.

Endpointy `/api/analytics/products`, `/api/analytics/recent-events` i `/api/analytics/funnel` również przyjmują opcjonalne `date_from` i `date_to` jako włączne granice dni UTC. Historia zdarzeń obsługuje dodatkowo parametr `limit`: domyślnie `20`, minimum `1`, maksimum `100`. Zwraca identyfikator i czas zdarzenia, typ, stronę oraz opcjonalnie element, identyfikator produktu i jego nazwę. Nie zwraca tokenu sesji ani całego pola `metadata`.

Lejek analizuje unikalne pary `(session_id, product_id)`. Para jest liczona jako wyświetlona po wystąpieniu `view_item`, a jako skonwertowana, gdy później w tej samej sesji wystąpi `add_to_cart` tego samego produktu. Kolejność wynika z `created_at`, a przy równych znacznikach czasu z `events.id`. Oba zdarzenia muszą należeć do wybranego zakresu dat, dlatego wynik dla wąskiego okresu nie przedstawia pełnej historycznej konwersji sesji. Wskaźnik nie oznacza rzeczywistych zakupów ani konwersji unikalnych użytkowników.

Wszystkie endpointy `/api/analytics/*` oraz diagnostyczny `/api/db-test` wymagają ważnej sesji właściciela. `POST /api/events` pozostaje publiczny, aby demonstracyjny sklep mógł rejestrować aktywność odwiedzających.

Sesja logowania jest przechowywana w podpisanym ciasteczku `HttpOnly` z `SameSite=Strict`, ścieżką `/api` i ograniczonym czasem ważności. W HTTPS ciasteczko ma flagę `Secure`. Logowanie i wylogowanie sprawdzają nagłówek `Origin`, a błędne próby logowania podlegają prostemu limitowi w pamięci procesu.

Logowanie przyjmuje JSON z polami `username` i `password`. Login obsługuje Unicode, w tym polskie znaki. Błędne dane uwierzytelniające zwracają `401`, niepoprawna struktura żądania zwraca `422` ze stałym komunikatem bez danych wejściowych, a niedozwolony lub brakujący `Origin` powoduje `403`. Brak wymaganej konfiguracji zamyka dostęp do analityki kodem `503`. Endpoint stanu zwraca `{"authenticated": false}` również wtedy, gdy konfiguracja jest niedostępna.

Limiter dopuszcza łącznie najwyżej pięć nieudanych prób z ostatnich 15 minut i trwających weryfikacji na adres klienta. Rezerwacja jest atomowa w jednym procesie, a Argon2 działa poza blokadą. Po osiągnięciu limitu kolejne żądanie otrzymuje `429`. Poprawne logowanie zeruje wcześniejsze błędy, a wygasłe wpisy są usuwane przy następnej próbie. Limiter nie jest współdzielony między procesami.

Sesja właściciela wygasa domyślnie po 30 minutach od logowania i nie jest automatycznie przedłużana aktywnością. Jest niezależna od pseudonimowej sesji odwiedzającego sklep. Wylogowanie usuwa ciasteczko z bieżącej przeglądarki; skopiowany token pozostaje ważny do wygaśnięcia. Zmiana sekretu podpisu unieważnia wszystkie sesje właściciela.

Lokalne logowanie można sprawdzić przez `/dashboard/login` albo Swagger UI. Formularz wysyła dane do `/api/auth/login`, a po sukcesie przechodzi do `/dashboard`. Należy konsekwentnie używać tej samej nazwy hosta. Nie ma rejestracji, ról, odzyskiwania hasła ani kont odwiedzających.

## Dashboard — etapy 2–6

Panel ma responsywne menu z pięcioma sekcjami: Przegląd, Sesje, Strony i interakcje, Produkty oraz Zdarzenia. Sekcja Przegląd prezentuje rzeczywiste dane z chronionego API: sześć kart KPI, liniowy wykres aktywności oraz poziome wykresy typów zdarzeń i sześciu najpopularniejszych stron. Wykresy tworzy lokalna, wersjonowana biblioteka Chart.js 4.6.1. Znane adresy DemoShop są agregowane i wyświetlane jako polskie nazwy, a lokalne katalogi historycznych ścieżek nie są ujawniane.

Sekcja Sesje korzysta z `/api/analytics/sessions` i prezentuje liczbę sesji, średni oraz medianowy czas zarejestrowanej aktywności, średnią liczbę zdarzeń na sesję, liczbę sesji z jednym zdarzeniem i ich procentowy udział. Czas jest formatowany w sekundach i minutach. Osobne objaśnienie przypomina, że sesja nie oznacza unikalnej osoby, a czas aktywności jest odstępem między pierwszym i ostatnim zdarzeniem. Dla sesji z jednym zdarzeniem wynosi 0 sekund.

Sekcja Strony i interakcje pobiera równolegle `/api/analytics/pages` i `/api/analytics/clicks`. Pokazuje łączną liczbę odsłon i kliknięć, poziomy wykres popularności stron oraz tabelę najczęstszych interakcji z nazwą strony, elementem, celem i liczbą kliknięć. Współdzieli normalizację ścieżek z Przeglądem, agreguje równoważne adresy i nie ujawnia ścieżek lokalnego systemu plików. Tabela domyślnie pokazuje dziesięć pozycji i pozwala rozwinąć pełny ranking.

Sekcja Produkty pobiera równolegle `/api/analytics/products` i `/api/analytics/funnel`. Pokazuje liczbę zdarzeń `view_item` i `add_to_cart`, dwa niezależne rankingi oraz dwustopniowy lejek unikalnych par sesja–produkt. Wartości zdarzeń nie są utożsamiane z parami lejka. Tabela lejka prezentuje wyświetlone i skonwertowane pary oraz współczynnik przejścia dla każdego produktu.

Sekcja Zdarzenia pobiera `/api/analytics/recent-events` i przedstawia najnowsze wpisy w tabeli. Typy zdarzeń i znane strony otrzymują polskie etykiety, czas jest wyświetlany jawnie w UTC, a szczegóły ograniczają się do bezpiecznej nazwy produktu albo elementu interfejsu. Filtr obejmuje włączne dni UTC i pozwala wybrać 20, 50 lub 100 rekordów. Tabela nie pokazuje tokenów sesji, cookies, pełnych metadanych ani lokalnych ścieżek systemowych.

Plik `dashboard/assets/vendor/chart.js-4.6.1/chart.umd.min.js` jest obsługiwany przez FastAPI przed skryptem Dashboardu. Aplikacja nie pobiera biblioteki z CDN podczas działania. Dołączony `LICENSE.md` zachowuje warunki licencji MIT Chart.js.

Filtry `Od`–`Do` we wszystkich pięciu sekcjach wykorzystują włącznie traktowane zakresy dni UTC. Puste pola oznaczają cały dostępny okres. W sekcji Sesje statystyki są liczone wyłącznie ze zdarzeń mieszczących się w zakresie, więc mogą opisywać tylko fragment historycznej aktywności sesji. Interfejs waliduje odwrócony zakres, pokazuje stany ładowania, błędu i braku danych oraz nie pozwala starszej odpowiedzi zastąpić wyniku nowszego filtrowania. Wygaśnięcie sesji podczas pobierania danych kieruje do logowania.

Dokumenty HTML są publicznymi szkieletami i nie zawierają danych analitycznych. Po otwarciu panel pokazuje stan ładowania i sprawdza `/api/auth/status`; brak aktywnej sesji kieruje do logowania. Kontrola jest ponawiana przy powrocie do karty, zmianie sekcji i co minutę w widocznej karcie. Przycisk wylogowania korzysta z istniejącego `/api/auth/logout`. Błędy połączenia mają czytelne komunikaty, a kontrolę sesji można ponowić.

Minutowa kontrola dotyczy wyłącznie ważności sesji właściciela. Nie pobiera ponownie danych analitycznych i nie odtwarza wykresów, gdy użytkownik pozostaje bezczynny. Dane Przeglądu są odświeżane po otwarciu sekcji, zmianie filtra albo ponownym wejściu do panelu.

Żądania używają względnych adresów same-origin i ciasteczka `HttpOnly` z niezmienionym `Path=/api`. Dashboard nie zapisuje loginu, hasła ani tokenu w Local Storage lub Session Storage i nie korzysta ze śledzenia aktywności sklepu. Ochrona danych nadal działa na serwerze API.

## Testy uwierzytelniania

W środowisku testowym z zainstalowanymi zależnościami backendu i biblioteką `httpx` wymaganą przez FastAPI TestClient uruchom:

```powershell
python -m unittest discover -s tests -p test_auth.py -v
```

Wszystkie testy backendu i integracji Dashboardu uruchamia polecenie `python -m unittest discover -s tests -v`. Pomocnicze funkcje interfejsu Przeglądu sprawdza `node --test tests/test_dashboard_ui.js`.

Testy używają generowanych w pamięci danych i atrap konfiguracji oraz zapisu. Nie odczytują `.env` ani nie zapisują rekordów do Neon. Obejmują walidację bez ujawniania hasła, Unicode, równoczesne próby, limit i wygasanie wpisów, cookie, wylogowanie oraz ochronę API.

## Pseudonimowa sesja

Przeglądarka przechowuje losowy, pseudonimowy `session_token` i czas ostatniej zarejestrowanej aktywności w Local Storage. W ramach aktywnej sesji ten sam token jest używany na wszystkich podstronach. Po co najmniej 30 minutach bez zarejestrowanej aktywności kolejne zdarzenie rozpoczyna nową sesję i otrzymuje nowy token.

Token nie zawiera imienia, adresu e-mail ani identyfikatora konta i sam nie wskazuje konkretnej osoby. Jest jednak identyfikatorem pseudonimowym, a nie gwarancją pełnej anonimowości. Liczba sesji nie jest równoznaczna z liczbą użytkowników.

## Zaimplementowane funkcjonalności

- responsywny serwis demonstracyjny i katalog ośmiu produktów;
- koszyk przechowywany w Local Storage;
- zdarzenia `page_view`, `click`, `view_item`, `add_to_cart` i `form_submit`;
- pseudonimowe sesje z limitem 30 minut bez aktywności;
- wysyłanie zdarzeń przez `fetch()` i obsługa błędów HTTP;
- walidacja znaczników czasu i normalizacja do UTC;
- zapis sesji, stron, typów zdarzeń i metadanych w PostgreSQL;
- podstawowe agregacje analityczne;
- filtrowanie aktywności i popularności stron według dat;
- statystyki sesji: liczba sesji, średnia i mediana czasu aktywności, sesje z jednym zdarzeniem oraz średnia liczba zdarzeń;
- ranking kliknięć grupowany według elementu, strony i opcjonalnego celu;
- historia ostatnich zdarzeń z kontrolowaną listą zwracanych pól;
- lejek interakcji `view_item` → `add_to_cart` dla par sesja–produkt;
- uwierzytelnianie jednego właściciela i ochrona API analitycznego;
- strona logowania i responsywny Dashboard z pięcioma pozycjami nawigacji;
- rzeczywiste KPI, wykres aktywności, rozkład zdarzeń, ranking stron i wspólny filtr dat w sekcji Przegląd;
- rzeczywiste wskaźniki sesji, udział sesji z jednym zdarzeniem i osobny filtr dat w sekcji Sesje.
- rzeczywiste KPI odsłon i kliknięć, wykres popularności stron oraz ranking interakcji w sekcji Strony i interakcje.
- rzeczywiste liczniki produktów, rankingi i lejek par sesja–produkt w sekcji Produkty.
- tabela ostatnich zdarzeń z polskimi etykietami, czasem UTC, limitem wyników i filtrem dat w sekcji Zdarzenia.

## Planowany rozwój

Poniższe funkcjonalności nie są jeszcze zaimplementowane:

- ewentualne dalsze wizualizacje sesji, jeśli backend zostanie rozszerzony o odpowiednie dane;
- rozbudowane filtry według dat, stron, typów zdarzeń i produktów;
- docelowa konfiguracja CORS i HTTPS dla adresów wdrożeniowych;
- wdrożenie backendu i frontendu w środowisku chmurowym.

Projekt nie jest obecnie przedstawiany jako wdrożony produkcyjnie.
