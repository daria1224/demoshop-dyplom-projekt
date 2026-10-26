import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


SESSION_COOKIE_NAME = "demoshop_owner_session"
SESSION_COOKIE_SALT = "demoshop-owner-session"
DEFAULT_SESSION_TTL_SECONDS = 30 * 60
MIN_SESSION_TTL_SECONDS = 5 * 60
MAX_SESSION_TTL_SECONDS = 24 * 60 * 60
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5500",
    "http://localhost:5500",
)


@dataclass(frozen=True)
class AuthSettings:
    username: str
    password_hash: str
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool


_password_hasher = PasswordHasher()
_failed_attempts: dict[str, deque[float]] = {}
_pending_attempts: dict[str, set[object]] = {}
_attempts_lock = threading.Lock()


def _read_session_ttl() -> int:
    raw_value = os.getenv("OWNER_SESSION_TTL_SECONDS", "")

    if not raw_value:
        return DEFAULT_SESSION_TTL_SECONDS

    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError("Nieprawidłowa konfiguracja uwierzytelniania.") from error

    if not MIN_SESSION_TTL_SECONDS <= value <= MAX_SESSION_TTL_SECONDS:
        raise RuntimeError("Nieprawidłowa konfiguracja uwierzytelniania.")

    return value


def get_auth_settings() -> AuthSettings:
    username = os.getenv("OWNER_USERNAME", "").strip()
    password_hash = os.getenv("OWNER_PASSWORD_HASH", "").strip()
    session_secret = os.getenv("OWNER_SESSION_SECRET", "")

    if (
        not username
        or not password_hash.startswith("$argon2")
        or len(session_secret) < 32
    ):
        raise RuntimeError("Brak wymaganej konfiguracji uwierzytelniania.")

    cookie_secure = os.getenv("AUTH_COOKIE_SECURE", "true").lower() not in {
        "0",
        "false",
        "no",
    }

    return AuthSettings(
        username=username,
        password_hash=password_hash,
        session_secret=session_secret,
        session_ttl_seconds=_read_session_ttl(),
        cookie_secure=cookie_secure,
    )


def get_cors_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip() and origin.strip() != "*"
    ]
    return origins or list(DEFAULT_CORS_ORIGINS)


def get_auth_origins() -> set[str]:
    configured = os.getenv("AUTH_ALLOWED_ORIGINS", "")
    return {
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip() and origin.strip() != "*"
    }


def _serializer(settings: AuthSettings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.session_secret,
        salt=SESSION_COOKIE_SALT,
    )


def _configuration_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Uwierzytelnianie właściciela jest niedostępne.",
    )


def _get_settings_or_error() -> AuthSettings:
    try:
        return get_auth_settings()
    except RuntimeError as error:
        raise _configuration_error() from error


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    return origin.rstrip("/") if origin else None


def require_trusted_origin(request: Request) -> None:
    origin = _request_origin(request)
    request_origin = str(request.base_url).rstrip("/")
    allowed_origins = {request_origin, *get_auth_origins()}

    if origin not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Żądanie pochodzi z niedozwolonego źródła.",
        )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _prune_attempts(attempts: deque[float], now: float) -> None:
    cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()


def reserve_login_attempt(request: Request) -> tuple[str, object]:
    now = time.monotonic()
    key = _client_key(request)

    with _attempts_lock:
        for client_key, attempts in list(_failed_attempts.items()):
            _prune_attempts(attempts, now)
            if not attempts:
                del _failed_attempts[client_key]

        attempts = _failed_attempts.get(key, deque())
        pending = _pending_attempts.get(key, set())

        if len(attempts) + len(pending) >= LOGIN_ATTEMPT_LIMIT:
            retry_after = max(
                1,
                int(LOGIN_ATTEMPT_WINDOW_SECONDS - (now - attempts[0]))
                if attempts else 1,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Zbyt wiele prób logowania. Spróbuj ponownie później.",
                headers={"Retry-After": str(retry_after)},
            )

        reservation = object()
        _pending_attempts.setdefault(key, set()).add(reservation)
        return key, reservation


def finish_login_attempt(
    reservation: tuple[str, object],
    *,
    failed: bool = False,
    succeeded: bool = False,
) -> None:
    key, attempt = reservation
    with _attempts_lock:
        pending = _pending_attempts.get(key)
        if pending is None or attempt not in pending:
            return
        pending.remove(attempt)
        if not pending:
            del _pending_attempts[key]

        if succeeded:
            _failed_attempts.pop(key, None)
        elif failed:
            _failed_attempts.setdefault(key, deque()).append(time.monotonic())


def authenticate_owner(username: str, password: str) -> AuthSettings:
    settings = _get_settings_or_error()

    try:
        password_valid = _password_hasher.verify(settings.password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        password_valid = False

    username_valid = secrets.compare_digest(
        username.encode("utf-8"), settings.username.encode("utf-8")
    )

    if not username_valid or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowe dane logowania.",
        )

    return settings


def create_session_cookie(response: Response, settings: AuthSettings) -> None:
    token = _serializer(settings).dumps(
        {
            "sub": settings.username,
            "sid": secrets.token_urlsafe(24),
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )


def delete_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/api",
    )


def require_owner(request: Request) -> str:
    settings = _get_settings_or_error()
    token = request.cookies.get(SESSION_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wymagane jest zalogowanie właściciela.",
        )

    try:
        payload = _serializer(settings).loads(
            token,
            max_age=settings.session_ttl_seconds,
        )
    except (BadSignature, SignatureExpired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesja logowania jest nieprawidłowa lub wygasła.",
        )

    subject = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(subject, str) or not secrets.compare_digest(
        subject.encode("utf-8"),
        settings.username.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesja logowania jest nieprawidłowa lub wygasła.",
        )

    return subject


def authentication_status(request: Request) -> bool:
    try:
        require_owner(request)
    except HTTPException:
        return False

    return True
