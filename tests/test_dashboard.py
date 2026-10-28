import secrets
import time
import unittest
from unittest.mock import patch

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

with patch("dotenv.load_dotenv"):
    from backend import auth, main


class DashboardTests(unittest.TestCase):
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
        for module in (auth, main):
            settings_patch = patch.object(
                module, "get_auth_settings", return_value=self.settings
            )
            settings_patch.start()
            self.addCleanup(settings_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def login(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": self.settings.username, "password": self.password},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_public_html_and_static_assets(self):
        for path in ("/dashboard/login", "/dashboard"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn(self.password, response.text)
            self.assertNotIn(self.settings.session_secret, response.text)
            self.assertNotIn("/js/main.js", response.text)
        for file, content_type in (
            ("dashboard.css", "text/css"),
            ("dashboard.js", "javascript"),
            ("vendor/chart.js-4.6.1/chart.umd.min.js", "javascript"),
            ("vendor/chart.js-4.6.1/LICENSE.md", "text/markdown"),
        ):
            response = self.client.get("/dashboard/assets/" + file)
            self.assertEqual(response.status_code, 200)
            self.assertIn(content_type, response.headers["content-type"])
        self.assertEqual(
            self.client.get("/dashboard/assets/.env").status_code, 404
        )

    def test_session_flow_and_cookie_path(self):
        self.assertFalse(self.client.get("/api/auth/status").json()["authenticated"])
        response = self.login()
        self.assertIn("Path=/api", response.headers["set-cookie"])
        self.assertTrue(self.client.get("/api/auth/status").json()["authenticated"])
        page = self.client.get("/dashboard")
        self.assertNotIn(auth.SESSION_COOKIE_NAME, page.request.headers.get("cookie", ""))
        response = self.client.post(
            "/api/auth/logout", headers={"Origin": "http://testserver"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.get("/api/auth/status").json()["authenticated"])
        self.assertEqual(self.client.get("/api/analytics/summary").status_code, 401)

    def test_expired_session(self):
        old_time = time.time() - self.settings.session_ttl_seconds - 2
        with patch("itsdangerous.timed.time.time", return_value=old_time):
            token = auth._serializer(self.settings).dumps(
                {"sub": self.settings.username, "sid": "expired-test"}
            )
        self.client.cookies.set(auth.SESSION_COOKIE_NAME, token, path="/api")
        self.assertFalse(self.client.get("/api/auth/status").json()["authenticated"])
        self.assertEqual(self.client.get("/api/analytics/summary").status_code, 401)

    def test_all_analytics_responses_remain_available_after_login(self):
        self.login()
        endpoints = {
            "summary": "get_analytics_summary",
            "events": "get_events_by_type",
            "products": "get_product_analytics",
            "activity": "get_activity_by_day",
            "pages": "get_page_analytics",
            "sessions": "get_session_analytics",
            "clicks": "get_click_analytics",
            "recent-events": "get_recent_events",
            "funnel": "get_product_funnel",
        }
        for endpoint, function in endpoints.items():
            with self.subTest(endpoint=endpoint):
                with patch.object(main, function, return_value={"test": True}) as query:
                    response = self.client.get("/api/analytics/" + endpoint)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {"test": True})
                    query.assert_called_once()

    def test_overview_filters_reach_all_analytics_queries(self):
        self.login()
        filters = {"date_from": "2026-01-02", "date_to": "2026-01-05"}
        targets = {
            "/api/analytics/summary": "get_analytics_summary",
            "/api/analytics/events": "get_events_by_type",
            "/api/analytics/activity": "get_activity_by_day",
            "/api/analytics/pages": "get_page_analytics",
            "/api/analytics/sessions": "get_session_analytics",
        }
        for endpoint, function in targets.items():
            with self.subTest(endpoint=endpoint):
                with patch.object(main, function, return_value=[]) as query:
                    response = self.client.get(endpoint, params=filters)
                    self.assertEqual(response.status_code, 200)
                    query.assert_called_once()
                    arguments = query.call_args.kwargs
                    self.assertEqual(arguments["date_from"].isoformat(), "2026-01-02")
                    self.assertEqual(arguments["date_to"].isoformat(), "2026-01-05")

        response = self.client.get(
            "/api/analytics/summary",
            params={"date_from": "2026-01-05", "date_to": "2026-01-02"},
        )
        self.assertEqual(response.status_code, 422)

        schema = self.client.get("/openapi.json").json()
        for endpoint in targets:
            parameter_names = {
                parameter["name"]
                for parameter in schema["paths"][endpoint]["get"]["parameters"]
            }
            self.assertTrue({"date_from", "date_to"}.issubset(parameter_names))

    def test_sessions_endpoint_contract_and_dashboard_markup(self):
        self.login()
        payload = {
            "session_count": 4,
            "average_activity_duration_seconds": 75.5,
            "single_event_session_count": 1,
            "average_events_per_session": 2.5,
            "median_activity_duration_seconds": 45.0,
        }
        with patch.object(main, "get_session_analytics", return_value=payload):
            response = self.client.get(
                "/api/analytics/sessions",
                params={"date_from": "2026-02-01", "date_to": "2026-02-05"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

        invalid = self.client.get(
            "/api/analytics/sessions",
            params={"date_from": "2026-02-06", "date_to": "2026-02-05"},
        )
        self.assertEqual(invalid.status_code, 422)

        page = self.client.get("/dashboard")
        for marker in (
            'id="sessions-panel"',
            'id="sessions-date-filter"',
            'id="sessions-kpi-grid"',
            'id="single-session-share"',
            'id="sessions-loading"',
            'id="sessions-empty"',
            'id="sessions-error"',
        ):
            self.assertIn(marker, page.text)

    def test_pages_and_clicks_contract_and_dashboard_markup(self):
        self.login()
        filters = {"date_from": "2026-03-01", "date_to": "2026-03-05"}
        pages = [{"page": "/products.html", "view_count": 7}]
        clicks = [
            {
                "element": "navigation_link",
                "page": "/index.html",
                "target": "products.html",
                "click_count": 4,
            }
        ]
        with patch.object(main, "get_page_analytics", return_value=pages) as pages_query:
            response = self.client.get("/api/analytics/pages", params=filters)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), pages)
        self.assertEqual(pages_query.call_args.kwargs["date_from"].isoformat(), "2026-03-01")

        with patch.object(main, "get_click_analytics", return_value=clicks) as clicks_query:
            response = self.client.get("/api/analytics/clicks", params=filters)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), clicks)
        self.assertEqual(clicks_query.call_args.kwargs["date_to"].isoformat(), "2026-03-05")

        for endpoint in ("pages", "clicks"):
            invalid = self.client.get(
                f"/api/analytics/{endpoint}",
                params={"date_from": "2026-03-06", "date_to": "2026-03-05"},
            )
            self.assertEqual(invalid.status_code, 422)

        page = self.client.get("/dashboard")
        for marker in (
            'id="pages-panel"',
            'id="pages-date-filter"',
            'id="page-view-total"',
            'id="click-total"',
            'id="pages-detail-chart"',
            'id="interactions-table-body"',
            'id="pages-section-loading"',
            'id="pages-section-empty"',
            'id="pages-section-error"',
        ):
            self.assertIn(marker, page.text)


if __name__ == "__main__":
    unittest.main()
