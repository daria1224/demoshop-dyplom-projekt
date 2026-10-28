from datetime import date, datetime, timezone
from pathlib import Path

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
from pydantic import BaseModel, Field, field_validator

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
DASHBOARD_DIRECTORY = Path(__file__).resolve().parent.parent / "dashboard"
app.mount(
    "/dashboard/assets",
    StaticFiles(directory=DASHBOARD_DIRECTORY / "assets"),
    name="dashboard-assets",
)


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
    session_token: str
    event_type: str
    page: str
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp musi zawierać informację o strefie czasowej")

        return value.astimezone(timezone.utc)

    class Config:
        extra = "allow"


class OwnerLogin(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


@app.get("/")
def read_root():
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
    event_data = event.dict()
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
