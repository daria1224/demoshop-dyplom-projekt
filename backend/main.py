from collections import OrderedDict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import threading
import time
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.auth import (
    authenticate_owner,
    authentication_status,
    create_session_cookie,
    delete_session_cookie,
    finish_login_attempt,
    get_auth_settings,
    get_cors_origins,
    reserve_login_attempt,
    require_owner,
    require_trusted_origin,
)

from backend.database import (
    check_database_connection,
    get_activity_by_day,
    get_analytics_summary,
    get_click_analytics,
    get_events_by_type,
    get_page_analytics,
    get_product_analytics,
    get_product_funnel,
    get_recent_events,
    get_session_analytics,
    save_event,
)

app = FastAPI()
PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
DASHBOARD_DIRECTORY = PROJECT_DIRECTORY / "dashboard"
EVENT_REQUEST_MAX_BYTES = 16 * 1024
EVENT_RATE_LIMIT = 120
EVENT_RATE_WINDOW_SECONDS = 60
EVENT_RATE_MAX_CLIENTS = 4096
EVENT_TIMESTAMP_TOLERANCE = timedelta(days=7)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventRateLimiter:
    def __init__(self, limit: int, window_seconds: int, max_clients: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, client_id: str, now: float | None = None) -> int | None:
        current_time = time.monotonic() if now is None else now
        cutoff = current_time - self.window_seconds

        with self._lock:
            for key in list(self._requests):
                requests = self._requests[key]
                while requests and requests[0] <= cutoff:
                    requests.popleft()
                if not requests:
                    del self._requests[key]

            requests = self._requests.get(client_id)
            if requests is None:
                if len(self._requests) >= self.max_clients:
                    self._requests.popitem(last=False)
                requests = deque()
                self._requests[client_id] = requests
            else:
                self._requests.move_to_end(client_id)

            if len(requests) >= self.limit:
                retry_after = max(
                    1,
                    int(requests[0] + self.window_seconds - current_time) + 1,
                )
                return retry_after

            requests.append(current_time)
            return None

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()


event_rate_limiter = EventRateLimiter(
    EVENT_RATE_LIMIT,
    EVENT_RATE_WINDOW_SECONDS,
    EVENT_RATE_MAX_CLIENTS,
)


@app.middleware("http")
async def protect_public_event_endpoint(request: Request, call_next):
    if request.method == "POST" and request.url.path.rstrip("/") == "/api/events":
        client_id = request.client.host if request.client else "unknown"
        retry_after = event_rate_limiter.check(client_id)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Przekroczono limit zgłoszeń zdarzeń."},
                headers={"Retry-After": str(retry_after)},
            )

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                parsed_content_length = int(content_length)
                if parsed_content_length < 0:
                    raise ValueError
                if parsed_content_length > EVENT_REQUEST_MAX_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Żądanie zdarzenia jest zbyt duże."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Nieprawidłowy nagłówek Content-Length."},
                )

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > EVENT_REQUEST_MAX_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Żądanie zdarzenia jest zbyt duże."},
                )
            body.extend(chunk)
        request._body = bytes(body)

    return await call_next(request)
app.mount(
    "/css",
    StaticFiles(directory=PROJECT_DIRECTORY / "css"),
    name="shop-css",
)
app.mount(
    "/js",
    StaticFiles(directory=PROJECT_DIRECTORY / "js"),
    name="shop-js",
)
app.mount(
    "/dashboard/assets",
    StaticFiles(directory=DASHBOARD_DIRECTORY / "assets"),
    name="dashboard-assets",
)


def public_shop_page(filename: str) -> FileResponse:
    return FileResponse(PROJECT_DIRECTORY / filename)


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def shop_home_page():
    return public_shop_page("index.html")


@app.get("/products.html", include_in_schema=False)
def shop_products_page():
    return public_shop_page("products.html")


@app.get("/product.html", include_in_schema=False)
def shop_product_page():
    return public_shop_page("product.html")


@app.get("/cart.html", include_in_schema=False)
def shop_cart_page():
    return public_shop_page("cart.html")


@app.get("/about.html", include_in_schema=False)
def shop_about_page():
    return public_shop_page("about.html")


@app.get("/contact.html", include_in_schema=False)
def shop_contact_page():
    return public_shop_page("contact.html")


@app.get("/dashboard/login", include_in_schema=False)
def dashboard_login_page():
    return FileResponse(
        DASHBOARD_DIRECTORY / "login.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return FileResponse(
        DASHBOARD_DIRECTORY / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation(request: Request, error: RequestValidationError):
    if request.url.path.rstrip("/") == "/api/auth/login":
        return JSONResponse(
            status_code=422,
            content={"detail": "Nieprawidłowa struktura danych logowania."},
        )
    if request.url.path.rstrip("/") == "/api/events":
        return JSONResponse(
            status_code=422,
            content={"detail": "Nieprawidłowe dane zdarzenia."},
        )
    return await request_validation_exception_handler(request, error)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

analytics_router = APIRouter(
    prefix="/api/analytics",
    dependencies=[Depends(require_owner)],
)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_token: str = Field(min_length=1, max_length=128)
    event_type: Literal[
        "page_view",
        "click",
        "view_item",
        "add_to_cart",
        "form_submit",
    ]
    page: str = Field(min_length=1, max_length=512)
    timestamp: datetime
    title: str | None = Field(default=None, min_length=1, max_length=200)
    element: str | None = Field(default=None, min_length=1, max_length=100)
    destination: str | None = Field(default=None, min_length=1, max_length=512)
    product_id: str | None = Field(default=None, min_length=1, max_length=100)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    open: bool | None = None
    cart_count: int | None = Field(default=None, ge=0, le=10_000)
    form: Literal["contact"] | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp musi zawierać informację o strefie czasowej")

        normalized = value.astimezone(timezone.utc)
        now = utc_now()
        if abs(normalized - now) > EVENT_TIMESTAMP_TOLERANCE:
            raise ValueError(
                "timestamp musi mieścić się w zakresie 7 dni od czasu serwera"
            )

        return normalized

    @model_validator(mode="after")
    def validate_metadata_for_event_type(self):
        metadata_fields = {
            "title",
            "element",
            "destination",
            "product_id",
            "product_name",
            "open",
            "cart_count",
            "form",
        }
        present = {
            name for name in metadata_fields if getattr(self, name) is not None
        }
        allowed = {
            "page_view": {"title"},
            "click": {
                "element",
                "destination",
                "product_id",
                "product_name",
                "open",
            },
            "view_item": {"product_id", "product_name"},
            "add_to_cart": {"product_id", "product_name", "cart_count"},
            "form_submit": {"form"},
        }[self.event_type]
        required = {
            "page_view": {"title"},
            "click": {"element"},
            "view_item": {"product_id", "product_name"},
            "add_to_cart": {"product_id", "product_name", "cart_count"},
            "form_submit": {"form"},
        }[self.event_type]

        if not present <= allowed:
            raise ValueError("Niedozwolone metadane dla tego typu zdarzenia")
        if not required <= present:
            raise ValueError("Brak wymaganych metadanych dla tego typu zdarzenia")

        return self


class OwnerLogin(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


@app.get("/api/health")
def read_health():
    return {"message": "DemoShop API działa"}


@app.get("/api/db-test", dependencies=[Depends(require_owner)])
def test_database_connection():
    connected, message = check_database_connection()
    return {"connected": connected, "message": message}


@analytics_router.get("/summary")
def get_summary(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_analytics_summary(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać podsumowania analitycznego.",
        )


@analytics_router.get("/events")
def get_analytics_events(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_events_by_type(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać zdarzeń analitycznych.",
        )


@analytics_router.get("/products")
def get_analytics_products(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_product_analytics(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać danych produktów.",
        )


def validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from nie może być późniejsza niż date_to.",
        )


@analytics_router.get("/activity")
def get_analytics_activity(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_activity_by_day(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać aktywności w czasie.",
        )


@analytics_router.get("/pages")
def get_analytics_pages(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_page_analytics(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać popularności stron.",
        )


@analytics_router.get(
    "/sessions",
    summary="Statystyki sesji",
    description=(
        "Filtry date_from i date_to wybierają zdarzenia z włącznego zakresu "
        "dni UTC. Wynik obejmuje sesje mające co najmniej jedno zdarzenie "
        "w tym zakresie, a czas aktywności i liczba zdarzeń są liczone "
        "wyłącznie na podstawie zdarzeń należących do zakresu."
    ),
)
def get_analytics_sessions(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_session_analytics(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać analityki sesji.",
        )


@analytics_router.get(
    "/clicks",
    summary="Ranking klikanych elementów",
    description=(
        "Zwraca wyłącznie zdarzenia click, pogrupowane według elementu, "
        "opcjonalnego celu i strony. Filtry date_from i date_to są "
        "włącznymi granicami dni UTC."
    ),
)
def get_analytics_clicks(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_click_analytics(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać analityki kliknięć.",
        )


@analytics_router.get(
    "/recent-events",
    summary="Historia ostatnich zdarzeń",
    description=(
        "Zwraca najnowsze zdarzenia z bezpiecznym podzbiorem pól. "
        "Filtry date_from i date_to są włącznymi granicami dni UTC."
    ),
)
def get_analytics_recent_events(
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    validate_date_range(date_from, date_to)

    try:
        return get_recent_events(
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać historii zdarzeń.",
        )


@analytics_router.get(
    "/funnel",
    summary="Lejek interakcji z produktami",
    description=(
        "Jednostką analizy jest para sesja-produkt. Konwersja oznacza "
        "zdarzenie add_to_cart występujące po view_item tego samego produktu "
        "w tej samej sesji. Przy remisie czasu kolejność wyznacza identyfikator "
        "zdarzenia. Filtry dat obejmują włączne dni UTC i oba zdarzenia muszą "
        "należeć do wybranego zakresu."
    ),
)
def get_analytics_funnel(
    date_from: date | None = None,
    date_to: date | None = None,
):
    validate_date_range(date_from, date_to)

    try:
        return get_product_funnel(date_from=date_from, date_to=date_to)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać lejka produktów.",
        )


app.include_router(analytics_router)


@app.post("/api/auth/login")
def login_owner(credentials: OwnerLogin, request: Request, response: Response):
    require_trusted_origin(request)
    reservation = reserve_login_attempt(request)

    failed = False
    succeeded = False
    try:
        settings = authenticate_owner(credentials.username, credentials.password)
        succeeded = True
    except HTTPException as error:
        failed = error.status_code == 401
        raise
    finally:
        finish_login_attempt(reservation, failed=failed, succeeded=succeeded)

    create_session_cookie(response, settings)
    return {"authenticated": True}


@app.post("/api/auth/logout")
def logout_owner(
    request: Request,
    response: Response,
    _owner: str = Depends(require_owner),
):
    require_trusted_origin(request)
    delete_session_cookie(response, get_auth_settings())
    return {"authenticated": False}


@app.get("/api/auth/status")
def get_owner_authentication_status(request: Request):
    return {"authenticated": authentication_status(request)}


@app.post("/api/events")
def receive_event(event: Event):
    event_data = event.model_dump(exclude_none=True)
    required_fields = {"session_token", "event_type", "page", "timestamp"}
    metadata = {
        key: value
        for key, value in event_data.items()
        if key not in required_fields
    }

    try:
        save_event(
            session_token=event.session_token,
            event_type=event.event_type,
            page=event.page,
            created_at=event.timestamp,
            metadata=metadata,
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się zapisać zdarzenia w bazie danych.",
        )

    return {"message": "Zdarzenie zostało zapisane"}
