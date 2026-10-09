from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from backend.database import (
    check_database_connection,
    get_activity_by_day,
    get_analytics_summary,
    get_events_by_type,
    get_page_analytics,
    get_product_analytics,
    save_event,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
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


@app.get("/")
def read_root():
    return {"message": "DemoShop API działa"}


@app.get("/api/db-test")
def test_database_connection():
    connected, message = check_database_connection()
    return {"connected": connected, "message": message}


@app.get("/api/analytics/summary")
def get_summary():
    try:
        return get_analytics_summary()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać podsumowania analitycznego.",
        )


@app.get("/api/analytics/events")
def get_analytics_events():
    try:
        return get_events_by_type()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Nie udało się pobrać zdarzeń analitycznych.",
        )


@app.get("/api/analytics/products")
def get_analytics_products():
    try:
        return get_product_analytics()
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


@app.get("/api/analytics/activity")
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


@app.get("/api/analytics/pages")
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
