import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from argon2 import PasswordHasher
from fastapi import HTTPException, Request, Response
from fastapi.testclient import TestClient

# Testy nie odczytują lokalnej konfiguracji ani nie łączą się z Neon.
with patch("dotenv.load_dotenv"):
    from backend import auth, main


def login_request(host="127.0.0.1"):
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/api/auth/login",
        "headers": [(b"host", b"testserver"), (b"origin", b"http://testserver")],
        "client": (host, 12345),
        "query_string": b"",
    })


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.settings = auth.AuthSettings(
            username="właściciel",
            password_hash=PasswordHasher().hash(cls.password),
            session_secret=secrets.token_urlsafe(48),
            session_ttl_seconds=1800,
            cookie_secure=False,
        )

    def setUp(self):
        auth._failed_attempts.clear()
        auth._pending_attempts.clear()
        self.settings_patch = patch.object(
            auth, "get_auth_settings", return_value=self.settings
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        main_settings_patch = patch.object(
            main, "get_auth_settings", return_value=self.settings
        )
        main_settings_patch.start()
        self.addCleanup(main_settings_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def login(self, username=None, password=None):
        return self.client.post(
            "/api/auth/login",
            json={
                "username": username or self.settings.username,
                "password": password or self.password,
            },
            headers={"Origin": "http://testserver"},
        )

    def test_invalid_credentials_and_unicode(self):
        self.assertEqual(self.login(username="inny właściciel").status_code, 401)
        self.assertEqual(self.login(password=secrets.token_urlsafe(24)).status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(
            self.client.get("/api/auth/status").json(), {"authenticated": True}
        )

    def test_validation_never_echoes_request(self):
        marker = secrets.token_urlsafe(24)
        cases = [
            {"username": "owner", "password": marker * 30},
            {"username": "owner", "password": {marker: marker}},
            {"username": {marker: marker}, "password": marker},
            [{"password": marker}],
            marker,
            {"password": marker},
        ]
        for body in cases:
            with self.subTest(structure=type(body).__name__):
                response = self.client.post("/api/auth/login", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(marker, response.text)
                self.assertNotIn("input", response.text)
        response = self.client.post(
            "/api/auth/login",
            content='{"password":"' + marker,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(marker, response.text)
        # Pozostałe endpointy zachowują standardowy format walidacji.
        response = self.client.post("/api/events", json={})
        self.assertEqual(response.status_code, 422)
        self.assertIsInstance(response.json()["detail"], list)

    def test_cookie_logout_and_api(self):
        paths = [
            route.path for route in main.app.routes
            if getattr(route, "path", "").startswith("/api/analytics/")
        ]
        self.assertEqual(len(paths), 9)
        for path in [*paths, "/api/db-test"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        response = self.login()
        cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "path=/api", "max-age=1800"):
            self.assertIn(flag, cookie)
        with patch.object(main, "get_analytics_summary", return_value={"total_events": 0}):
            self.assertEqual(self.client.get("/api/analytics/summary").status_code, 200)
        self.assertEqual(self.client.post(
            "/api/auth/logout", headers={"Origin": "http://testserver"}
        ).status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/summary").status_code, 401)
        with patch.object(main, "save_event") as save:
            response = self.client.post("/api/events", json={
                "session_token": "isolated-test",
                "event_type": "page_view",
                "page": "/",
                "timestamp": "2026-10-26T10:00:00Z",
            })
            self.assertEqual(response.status_code, 200)
            save.assert_called_once()

    def test_concurrent_failures_reserve_only_five_slots(self):
        entered = threading.Barrier(5)
        release = threading.Event()

        def reject(*args):
            entered.wait(timeout=10)
            release.wait(timeout=10)
            raise HTTPException(status_code=401, detail="Nieprawidłowe dane logowania.")

        def attempt():
            try:
                main.login_owner(
                    main.OwnerLogin(username="owner", password=self.password),
                    login_request(), Response(),
                )
            except HTTPException as error:
                return error.status_code

        with patch.object(main, "authenticate_owner", side_effect=reject):
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(attempt) for _ in range(10)]
                # Pięć odrzuconych żądań musi zakończyć się, gdy Argon2 pozostałych trwa.
                from concurrent.futures import wait, FIRST_COMPLETED
                rejected = set()
                while len(rejected) < 5:
                    done, _ = wait(
                        [future for future in futures if future not in rejected],
                        timeout=10, return_when=FIRST_COMPLETED,
                    )
                    self.assertTrue(done)
                    rejected.update(done)
                self.assertTrue(all(future.result() == 429 for future in rejected))
                release.set()
                statuses = [future.result(timeout=10) for future in futures]
        self.assertEqual(statuses.count(401), 5)
        self.assertEqual(statuses.count(429), 5)
        self.assertFalse(auth._pending_attempts)
        self.assertEqual(self.login().status_code, 200)  # Inny adres klienta.

    def test_expiry_cleanup_and_success_release(self):
        with patch.object(auth.time, "monotonic", return_value=1000):
            for host in ("old-a", "old-b"):
                for _ in range(5):
                    reservation = auth.reserve_login_attempt(login_request(host))
                    auth.finish_login_attempt(reservation, failed=True)
            with self.assertRaises(HTTPException) as caught:
                auth.reserve_login_attempt(login_request("old-a"))
            self.assertEqual(caught.exception.status_code, 429)
        with patch.object(auth.time, "monotonic", return_value=1900):
            reservation = auth.reserve_login_attempt(login_request("new"))
            self.assertFalse(auth._failed_attempts)
            auth.finish_login_attempt(reservation, succeeded=True)
            self.assertFalse(auth._pending_attempts)
        for _ in range(8):
            reservation = auth.reserve_login_attempt(login_request())
            auth.finish_login_attempt(reservation, succeeded=True)
        self.assertFalse(auth._failed_attempts)
        self.assertFalse(auth._pending_attempts)

    def test_configuration_error_releases_reservation(self):
        with patch.object(main, "authenticate_owner", side_effect=HTTPException(503)):
            self.assertEqual(self.login().status_code, 503)
        self.assertFalse(auth._pending_attempts)
        self.assertFalse(auth._failed_attempts)

    def test_http_limit_and_success_reset(self):
        wrong_password = secrets.token_urlsafe(24)
        for _ in range(4):
            self.assertEqual(self.login(password=wrong_password).status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        for _ in range(5):
            self.assertEqual(self.login(password=wrong_password).status_code, 401)
        response = self.login(password=wrong_password)
        self.assertEqual(response.status_code, 429)
        self.assertIn("retry-after", response.headers)


if __name__ == "__main__":
    unittest.main()
