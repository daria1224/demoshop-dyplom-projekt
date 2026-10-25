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
- Local Storage;
- Python 3.13;
- FastAPI i Pydantic;
- Uvicorn;
- psycopg 3;
- PostgreSQL w usłudze Neon;
- SQL i typ `JSONB` dla dodatkowych danych zdarzeń.

## Struktura projektu

```text
demoshop/
├── backend/
│   ├── database.py       # połączenie z PostgreSQL i zapytania SQL
│   ├── main.py           # aplikacja FastAPI i endpointy
│   └── schema.sql        # definicje tabel bazy danych
├── css/
│   ├── cart.css          # style strony koszyka
│   └── style.css         # wspólne style serwisu
├── js/
│   ├── main.js           # interakcje, koszyk i rejestrowanie zdarzeń
│   └── products.js       # demonstracyjny katalog produktów
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
```

Wstaw własny adres połączenia otrzymany od dostawcy PostgreSQL. Plik `.env` jest ignorowany przez Git i nie powinien być publikowany.

Dla nowej bazy wykonaj polecenia z `backend/schema.sql`, na przykład w edytorze SQL Neon. Nie wykonuj ich ponownie na bazie, w której tabele już istnieją.

### 3. Backend

Uruchom FastAPI z katalogu głównego projektu:

```powershell
python -m uvicorn backend.main:app --reload
```

API będzie dostępne pod adresem `http://127.0.0.1:8000`, a interaktywna dokumentacja pod `http://127.0.0.1:8000/docs`.

### 4. Frontend

W drugim terminalu uruchom prosty serwer plików statycznych:

```powershell
python -m http.server 5500
```

Otwórz `http://127.0.0.1:5500` w przeglądarce. Obecny frontend wysyła zdarzenia do lokalnego adresu `http://127.0.0.1:8000/api/events`.

## Endpointy API

| Metoda | Ścieżka | Działanie |
|---|---|---|
| `GET` | `/` | Informacja o działaniu API |
| `GET` | `/api/db-test` | Kontrola połączenia z PostgreSQL |
| `POST` | `/api/events` | Walidacja i zapis pojedynczego zdarzenia |
| `GET` | `/api/analytics/summary` | Podstawowe liczniki zdarzeń i sesji |
| `GET` | `/api/analytics/events` | Liczba zdarzeń według typu |
| `GET` | `/api/analytics/products` | Wyświetlenia produktów i dodania do koszyka |
| `GET` | `/api/analytics/activity` | Liczba wszystkich zdarzeń według dnia UTC |
| `GET` | `/api/analytics/pages` | Liczba odsłon stron na podstawie `page_view` |
| `GET` | `/api/analytics/sessions` | Liczba sesji oraz statystyki zarejestrowanej aktywności |
| `GET` | `/api/analytics/clicks` | Ranking klikanych elementów według strony i celu |

Endpointy `/api/analytics/activity` i `/api/analytics/pages` przyjmują opcjonalne parametry `date_from` i `date_to` w formacie `YYYY-MM-DD`. Granice są włączne i odnoszą się do dni w UTC. Pełny przedział w `/activity` zawiera także dni bez zdarzeń, z wartością `0`.

Endpointy `/api/analytics/sessions` i `/api/analytics/clicks` obsługują te same opcjonalne granice dni UTC. W analityce sesji filtr wybiera zdarzenia z okresu, a statystyki każdej sesji są liczone wyłącznie na podstawie zdarzeń znajdujących się w tym okresie.

Endpointy analityczne nie są jeszcze chronione autoryzacją i nie powinny być publicznie udostępniane w obecnym stanie.

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
- ranking kliknięć grupowany według elementu, strony i opcjonalnego celu.

## Planowany rozwój

Poniższe funkcjonalności nie są jeszcze zaimplementowane:

- osobny Dashboard analityczny;
- autoryzacja właściciela i ochrona wszystkich endpointów analitycznych;
- wykresy aktywności, popularności stron i produktów;
- tabela ostatnich zdarzeń;
- dalsze wskaźniki oraz wizualizacje dotyczące sesji;
- rozbudowane filtry według dat, stron, typów zdarzeń i produktów;
- bezpieczna konfiguracja CORS dla docelowych adresów;
- wdrożenie backendu i frontendu w środowisku chmurowym.

Projekt nie jest obecnie przedstawiany jako wdrożony produkcyjnie.
