import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def _open_database_connection():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("Brak zmiennej DATABASE_URL w pliku .env.")

    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("Brakuje biblioteki psycopg.") from error

    return psycopg.connect(database_url, connect_timeout=5)


def check_database_connection() -> tuple[bool, str]:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        return False, "Brak zmiennej DATABASE_URL w pliku .env."

    try:
        import psycopg
    except ImportError:
        return False, "Brakuje biblioteki psycopg."

    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

        return True, "Połączenie z bazą PostgreSQL działa."
    except Exception:
        return False, "Nie udało się połączyć z bazą PostgreSQL."


def save_event(
    session_token: str,
    event_type: str,
    page: str,
    created_at: datetime,
    metadata: dict[str, object],
) -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("Brak zmiennej DATABASE_URL w pliku .env.")

    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as error:
        raise RuntimeError("Brakuje biblioteki psycopg.") from error

    connection = psycopg.connect(database_url, connect_timeout=5)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sessions (session_id, started_at, last_seen_at, user_agent)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET started_at = LEAST(sessions.started_at, EXCLUDED.started_at),
                    last_seen_at = GREATEST(sessions.last_seen_at, EXCLUDED.last_seen_at),
                    user_agent = COALESCE(EXCLUDED.user_agent, sessions.user_agent)
                RETURNING id
                """,
                (
                    session_token,
                    created_at,
                    created_at,
                    metadata.get("user_agent"),
                ),
            )
            session_id = cursor.fetchone()[0]

            page_title = metadata.get("title") or page
            has_page_title = "title" in metadata
            cursor.execute(
                """
                INSERT INTO pages (url, title)
                VALUES (%s, %s)
                ON CONFLICT (url) DO UPDATE
                SET title = CASE
                    WHEN %s THEN EXCLUDED.title
                    ELSE pages.title
                END
                RETURNING id
                """,
                (page, page_title, has_page_title),
            )
            page_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO event_types (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (event_type,),
            )
            event_type_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO events (
                    session_id,
                    page_id,
                    event_type_id,
                    element_name,
                    metadata,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    page_id,
                    event_type_id,
                    metadata.get("element"),
                    Jsonb(metadata),
                    created_at,
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_analytics_summary() -> dict[str, int]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT e.session_id) AS total_sessions,
                    COUNT(*) FILTER (WHERE et.name = 'page_view') AS page_views,
                    COUNT(*) FILTER (WHERE et.name = 'click') AS clicks,
                    COUNT(*) FILTER (WHERE et.name = 'view_item') AS product_views,
                    COUNT(*) FILTER (WHERE et.name = 'add_to_cart') AS add_to_cart
                FROM events e
                JOIN event_types et ON et.id = e.event_type_id
                """
            )
            row = cursor.fetchone()

        return {
            "total_events": row[0],
            "total_sessions": row[1],
            "page_views": row[2],
            "clicks": row[3],
            "product_views": row[4],
            "add_to_cart": row[5],
        }
    finally:
        connection.close()


def get_events_by_type() -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT et.name, COUNT(e.id) AS event_count
                FROM event_types et
                JOIN events e ON e.event_type_id = et.id
                GROUP BY et.name
                ORDER BY event_count DESC, et.name
                """
            )
            rows = cursor.fetchall()

        return [
            {"event_type": row[0], "event_count": row[1]}
            for row in rows
        ]
    finally:
        connection.close()


def get_product_analytics() -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    e.metadata ->> 'product_name' AS product_name,
                    e.metadata ->> 'product_id' AS product_id,
                    COUNT(*) FILTER (WHERE et.name = 'view_item') AS view_count,
                    COUNT(*) FILTER (WHERE et.name = 'add_to_cart') AS add_to_cart_count
                FROM events e
                JOIN event_types et ON et.id = e.event_type_id
                WHERE et.name IN (%s, %s)
                    AND e.metadata ->> 'product_id' IS NOT NULL
                GROUP BY
                    e.metadata ->> 'product_name',
                    e.metadata ->> 'product_id'
                ORDER BY product_name NULLS LAST, product_id
                """,
                ("view_item", "add_to_cart"),
            )
            rows = cursor.fetchall()

        return [
            {
                "product_name": row[0],
                "product_id": row[1],
                "view_count": row[2],
                "add_to_cart_count": row[3],
            }
            for row in rows
        ]
    finally:
        connection.close()


def _build_event_date_filter(
    date_from: date | None,
    date_to: date | None,
) -> tuple[str, list[date]]:
    conditions = []
    parameters = []
    event_date = "(e.created_at AT TIME ZONE 'UTC')::date"

    if date_from:
        conditions.append(f"{event_date} >= %s")
        parameters.append(date_from)

    if date_to:
        conditions.append(f"{event_date} <= %s")
        parameters.append(date_to)

    if not conditions:
        return "", parameters

    return "WHERE " + " AND ".join(conditions), parameters


def get_activity_by_day(
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            if date_from and date_to:
                cursor.execute(
                    """
                    WITH days AS (
                        SELECT day::date
                        FROM generate_series(
                            %s::date,
                            %s::date,
                            INTERVAL '1 day'
                        ) AS series(day)
                    ),
                    daily_counts AS (
                        SELECT
                            (e.created_at AT TIME ZONE 'UTC')::date AS day,
                            COUNT(*) AS event_count
                        FROM events e
                        WHERE (e.created_at AT TIME ZONE 'UTC')::date >= %s
                            AND (e.created_at AT TIME ZONE 'UTC')::date <= %s
                        GROUP BY day
                    )
                    SELECT days.day, COALESCE(daily_counts.event_count, 0)
                    FROM days
                    LEFT JOIN daily_counts ON daily_counts.day = days.day
                    ORDER BY days.day
                    """,
                    (date_from, date_to, date_from, date_to),
                )
            else:
                date_filter, parameters = _build_event_date_filter(
                    date_from,
                    date_to,
                )
                cursor.execute(
                    f"""
                    SELECT
                        (e.created_at AT TIME ZONE 'UTC')::date AS day,
                        COUNT(*) AS event_count
                    FROM events e
                    {date_filter}
                    GROUP BY day
                    ORDER BY day
                    """,
                    parameters,
                )

            rows = cursor.fetchall()

        return [
            {"date": row[0].isoformat(), "event_count": row[1]}
            for row in rows
        ]
    finally:
        connection.close()


def get_page_analytics(
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            date_filter, date_parameters = _build_event_date_filter(
                date_from,
                date_to,
            )
            date_conditions = date_filter.removeprefix("WHERE ")
            additional_filter = (
                f" AND {date_conditions}" if date_conditions else ""
            )

            cursor.execute(
                f"""
                SELECT p.url, COUNT(*) AS view_count
                FROM events e
                JOIN pages p ON p.id = e.page_id
                JOIN event_types et ON et.id = e.event_type_id
                WHERE et.name = %s
                    {additional_filter}
                GROUP BY p.url
                ORDER BY view_count DESC, p.url
                """,
                ["page_view", *date_parameters],
            )
            rows = cursor.fetchall()

        return [
            {"page": row[0], "view_count": row[1]}
            for row in rows
        ]
    finally:
        connection.close()


def get_session_analytics(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int | float]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            date_filter, parameters = _build_event_date_filter(
                date_from,
                date_to,
            )
            cursor.execute(
                f"""
                WITH session_metrics AS (
                    SELECT
                        s.id AS session_id,
                        COUNT(e.id) AS event_count,
                        EXTRACT(
                            EPOCH FROM (MAX(e.created_at) - MIN(e.created_at))
                        ) AS activity_duration_seconds
                    FROM sessions s
                    JOIN events e ON e.session_id = s.id
                    {date_filter}
                    GROUP BY s.id
                )
                SELECT
                    COUNT(*) AS session_count,
                    AVG(activity_duration_seconds) AS average_duration,
                    COUNT(*) FILTER (
                        WHERE event_count = 1
                    ) AS single_event_session_count,
                    AVG(event_count) AS average_events,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY activity_duration_seconds
                    ) AS median_duration
                FROM session_metrics
                """,
                parameters,
            )
            row = cursor.fetchone()

        return {
            "session_count": int(row[0]),
            "average_activity_duration_seconds": round(float(row[1] or 0), 2),
            "single_event_session_count": int(row[2]),
            "average_events_per_session": round(float(row[3] or 0), 2),
            "median_activity_duration_seconds": round(float(row[4] or 0), 2),
        }
    finally:
        connection.close()


def get_click_analytics(
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            date_filter, date_parameters = _build_event_date_filter(
                date_from,
                date_to,
            )
            date_conditions = date_filter.removeprefix("WHERE ")
            additional_filter = (
                f" AND {date_conditions}" if date_conditions else ""
            )

            cursor.execute(
                f"""
                SELECT
                    COALESCE(
                        NULLIF(e.element_name, ''),
                        NULLIF(e.metadata ->> 'element', ''),
                        'unknown'
                    ) AS element,
                    p.url AS page,
                    COALESCE(
                        NULLIF(e.metadata ->> 'product_id', ''),
                        NULLIF(e.metadata ->> 'destination', '')
                    ) AS target,
                    COUNT(*) AS click_count
                FROM events e
                JOIN pages p ON p.id = e.page_id
                JOIN event_types et ON et.id = e.event_type_id
                WHERE et.name = %s
                    {additional_filter}
                GROUP BY element, p.url, target
                ORDER BY
                    click_count DESC,
                    element,
                    p.url,
                    target NULLS LAST
                """,
                ["click", *date_parameters],
            )
            rows = cursor.fetchall()

        return [
            {
                "element": row[0],
                "page": row[1],
                "target": row[2],
                "click_count": row[3],
            }
            for row in rows
        ]
    finally:
        connection.close()


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_recent_events(
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            date_filter, date_parameters = _build_event_date_filter(
                date_from,
                date_to,
            )
            cursor.execute(
                f"""
                SELECT
                    e.id,
                    e.created_at,
                    et.name AS event_type,
                    p.url AS page,
                    COALESCE(
                        NULLIF(e.element_name, ''),
                        NULLIF(e.metadata ->> 'element', '')
                    ) AS element,
                    NULLIF(e.metadata ->> 'product_id', '') AS product_id,
                    NULLIF(e.metadata ->> 'product_name', '') AS product_name
                FROM events e
                JOIN pages p ON p.id = e.page_id
                JOIN event_types et ON et.id = e.event_type_id
                {date_filter}
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT %s
                """,
                [*date_parameters, limit],
            )
            rows = cursor.fetchall()

        return [
            {
                "event_id": row[0],
                "timestamp": _format_utc_timestamp(row[1]),
                "event_type": row[2],
                "page": row[3],
                "element": row[4],
                "product_id": row[5],
                "product_name": row[6],
            }
            for row in rows
        ]
    finally:
        connection.close()


def get_product_funnel(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    connection = _open_database_connection()

    try:
        with connection.cursor() as cursor:
            date_filter, date_parameters = _build_event_date_filter(
                date_from,
                date_to,
            )
            date_conditions = date_filter.removeprefix("WHERE ")
            additional_filter = (
                f" AND {date_conditions}" if date_conditions else ""
            )
            cursor.execute(
                f"""
                WITH filtered_events AS (
                    SELECT
                        e.id,
                        e.session_id,
                        e.created_at,
                        et.name AS event_type,
                        e.metadata ->> 'product_id' AS product_id,
                        NULLIF(e.metadata ->> 'product_name', '') AS product_name
                    FROM events e
                    JOIN event_types et ON et.id = e.event_type_id
                    WHERE et.name IN (%s, %s)
                        AND NULLIF(e.metadata ->> 'product_id', '') IS NOT NULL
                        {additional_filter}
                ),
                viewed_pairs AS (
                    SELECT
                        view_event.session_id,
                        view_event.product_id,
                        MAX(view_event.product_name) AS product_name,
                        BOOL_OR(
                            EXISTS (
                                SELECT 1
                                FROM filtered_events add_event
                                WHERE add_event.session_id = view_event.session_id
                                    AND add_event.product_id = view_event.product_id
                                    AND add_event.event_type = %s
                                    AND (
                                        add_event.created_at,
                                        add_event.id
                                    ) > (
                                        view_event.created_at,
                                        view_event.id
                                    )
                            )
                        ) AS converted
                    FROM filtered_events view_event
                    WHERE view_event.event_type = %s
                    GROUP BY view_event.session_id, view_event.product_id
                ),
                product_metrics AS (
                    SELECT
                        product_id,
                        MAX(product_name) AS product_name,
                        COUNT(*) AS viewed_pairs,
                        COUNT(*) FILTER (WHERE converted) AS converted_pairs
                    FROM viewed_pairs
                    GROUP BY product_id
                )
                SELECT
                    product_id,
                    product_name,
                    viewed_pairs,
                    converted_pairs
                FROM product_metrics
                ORDER BY viewed_pairs DESC, product_id
                """,
                [
                    "view_item",
                    "add_to_cart",
                    *date_parameters,
                    "add_to_cart",
                    "view_item",
                ],
            )
            rows = cursor.fetchall()

        products = []
        total_viewed = 0
        total_converted = 0

        for row in rows:
            viewed_pairs = int(row[2])
            converted_pairs = int(row[3])
            total_viewed += viewed_pairs
            total_converted += converted_pairs
            products.append(
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "viewed_session_product_pairs": viewed_pairs,
                    "converted_session_product_pairs": converted_pairs,
                    "conversion_rate_percent": round(
                        converted_pairs / viewed_pairs * 100,
                        2,
                    ),
                }
            )

        conversion_rate = (
            round(total_converted / total_viewed * 100, 2)
            if total_viewed
            else 0.0
        )

        return {
            "viewed_session_product_pairs": total_viewed,
            "converted_session_product_pairs": total_converted,
            "conversion_rate_percent": conversion_rate,
            "products": products,
        }
    finally:
        connection.close()
