import secrets
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

with patch("dotenv.load_dotenv"):
    from backend import auth, database, main


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

        dashboard = self.client.get("/dashboard").text
        script = self.client.get("/dashboard/assets/dashboard.js").text
        self.assertNotIn('id="section-panel"', dashboard)
        self.assertNotIn("section-topics", dashboard)
        self.assertNotIn("placeholderPanel", script)
        self.assertNotIn("section.topics", script)

    def test_public_shop_pages_and_assets_use_one_origin(self):
        pages = {
            "/": "DemoShop",
            "/index.html": "DemoShop",
            "/products.html": "Produkty",
            "/product.html?id=kubek-aurora": "Produkt",
            "/cart.html": "Koszyk",
            "/about.html": "O nas",
            "/contact.html": "Kontakt",
        }
        for path, expected_text in pages.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertIn(expected_text, response.text)

        for path, content_type in (
            ("/css/style.css", "text/css"),
            ("/css/cart.css", "text/css"),
            ("/js/products.js", "javascript"),
            ("/js/main.js", "javascript"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(content_type, response.headers["content-type"])

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"message": "DemoShop API działa"})

    def test_private_project_files_are_not_public(self):
        for path in (
            "/.env",
            "/README.md",
            "/spec.md",
            "/requirements.txt",
            "/backend/main.py",
            "/backend/schema.sql",
            "/tests/test_dashboard.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_shop_uses_relative_event_api_and_single_page_view_registration(self):
        script = self.client.get("/js/main.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("fetch('/api/events'", script.text)
        self.assertIn("keepalive: true", script.text)
        self.assertNotIn("127.0.0.1", script.text)
        self.assertNotIn("localhost", script.text)
        self.assertEqual(script.text.count("trackEvent('page_view'"), 1)

        project_directory = Path(__file__).resolve().parent.parent
        for page_name in (
            "index.html",
            "products.html",
            "product.html",
            "cart.html",
            "about.html",
            "contact.html",
        ):
            page = (project_directory / page_name).read_text(encoding="utf-8")
            self.assertEqual(page.count('src="js/main.js"'), 1)

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

    def test_products_and_funnel_contract_and_dashboard_markup(self):
        self.login()
        products = [{
            "product_name": "Kubek Aurora",
            "product_id": "kubek-aurora",
            "view_count": 7,
            "add_to_cart_count": 3,
        }]
        funnel = {
            "viewed_session_product_pairs": 4,
            "converted_session_product_pairs": 2,
            "conversion_rate_percent": 50.0,
            "products": [],
        }
        filter_cases = (
            ({}, None, None),
            ({"date_from": "2026-04-01"}, "2026-04-01", None),
            ({"date_to": "2026-04-05"}, None, "2026-04-05"),
            (
                {"date_from": "2026-04-01", "date_to": "2026-04-05"},
                "2026-04-01",
                "2026-04-05",
            ),
        )
        for filters, expected_from, expected_to in filter_cases:
            with self.subTest(filters=filters):
                with patch.object(
                    main,
                    "get_product_analytics",
                    return_value=products,
                ) as product_query:
                    response = self.client.get(
                        "/api/analytics/products",
                        params=filters,
                    )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), products)
                arguments = product_query.call_args.kwargs
                actual_from = arguments["date_from"]
                actual_to = arguments["date_to"]
                self.assertEqual(
                    actual_from.isoformat() if actual_from else None,
                    expected_from,
                )
                self.assertEqual(
                    actual_to.isoformat() if actual_to else None,
                    expected_to,
                )

        with patch.object(
            main,
            "get_product_funnel",
            return_value=funnel,
        ) as funnel_query:
            response = self.client.get(
                "/api/analytics/funnel",
                params={"date_from": "2026-04-01", "date_to": "2026-04-05"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), funnel)
        self.assertEqual(
            funnel_query.call_args.kwargs["date_to"].isoformat(),
            "2026-04-05",
        )

        invalid = self.client.get(
            "/api/analytics/products",
            params={"date_from": "2026-04-06", "date_to": "2026-04-05"},
        )
        self.assertEqual(invalid.status_code, 422)

        schema = self.client.get("/openapi.json").json()
        product_parameters = {
            parameter["name"]
            for parameter in schema["paths"]["/api/analytics/products"]["get"][
                "parameters"
            ]
        }
        self.assertTrue({"date_from", "date_to"}.issubset(product_parameters))

        page = self.client.get("/dashboard")
        for label in (
            "Łączna liczba wyświetleń produktów",
            "Łączna liczba dodań produktów do koszyka",
            "Pary z wyświetleniem produktu",
            "Pary z późniejszym dodaniem do koszyka",
            "Wyświetlenia",
            "Dodania do koszyka",
            "Przejście (%)",
        ):
            self.assertIn(label, page.text)
        self.assertNotIn("Liczba zdarzeń <code>view_item</code>", page.text)
        self.assertNotIn("Liczba zdarzeń <code>add_to_cart</code>", page.text)
        for marker in (
            'id="products-panel"',
            'id="products-date-filter"',
            'id="product-views-total"',
            'id="add-to-cart-total"',
            'id="product-views-ranking"',
            'id="product-cart-ranking"',
            'id="funnel-rate"',
            'id="funnel-products-body"',
            'id="products-loading"',
            'id="products-empty"',
            'id="products-error"',
        ):
            self.assertIn(marker, page.text)

    def test_product_query_uses_parameterized_utc_day_filters(self):
        cases = (
            (None, None, ["view_item", "add_to_cart"], False, False),
            (
                date(2026, 4, 1),
                None,
                ["view_item", "add_to_cart", date(2026, 4, 1)],
                True,
                False,
            ),
            (
                None,
                date(2026, 4, 5),
                ["view_item", "add_to_cart", date(2026, 4, 5)],
                False,
                True,
            ),
            (
                date(2026, 4, 1),
                date(2026, 4, 5),
                [
                    "view_item",
                    "add_to_cart",
                    date(2026, 4, 1),
                    date(2026, 4, 5),
                ],
                True,
                True,
            ),
        )
        for date_from, date_to, expected_parameters, has_from, has_to in cases:
            with self.subTest(date_from=date_from, date_to=date_to):
                cursor = MagicMock()
                cursor.__enter__.return_value = cursor
                cursor.fetchall.return_value = []
                connection = MagicMock()
                connection.cursor.return_value = cursor
                with patch.object(
                    database,
                    "_open_database_connection",
                    return_value=connection,
                ):
                    result = database.get_product_analytics(date_from, date_to)

                self.assertEqual(result, [])
                query, parameters = cursor.execute.call_args.args
                self.assertEqual(parameters, expected_parameters)
                self.assertEqual("::date >= %s" in query, has_from)
                self.assertEqual("::date <= %s" in query, has_to)
                if has_from or has_to:
                    self.assertIn("AT TIME ZONE 'UTC'", query)
                else:
                    self.assertNotIn("AT TIME ZONE 'UTC'", query)
                connection.close.assert_called_once()

    def test_recent_events_contract_filters_limits_and_dashboard_markup(self):
        self.login()
        payload = [{
            "event_id": 17,
            "timestamp": "2026-05-03T10:15:30Z",
            "event_type": "view_item",
            "page": "/product.html",
            "element": "view_product_button",
            "product_id": "kubek-aurora",
            "product_name": "Kubek Aurora",
        }]
        with patch.object(main, "get_recent_events", return_value=payload) as query:
            response = self.client.get(
                "/api/analytics/recent-events",
                params={
                    "date_from": "2026-05-01",
                    "date_to": "2026-05-03",
                    "limit": 50,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        arguments = query.call_args.kwargs
        self.assertEqual(arguments["date_from"].isoformat(), "2026-05-01")
        self.assertEqual(arguments["date_to"].isoformat(), "2026-05-03")
        self.assertEqual(arguments["limit"], 50)

        for limit in (20, 50, 100):
            with self.subTest(limit=limit):
                with patch.object(main, "get_recent_events", return_value=[]):
                    response = self.client.get(
                        "/api/analytics/recent-events",
                        params={"limit": limit},
                    )
                self.assertEqual(response.status_code, 200)

        for invalid_limit in (0, 101):
            response = self.client.get(
                "/api/analytics/recent-events",
                params={"limit": invalid_limit},
            )
            self.assertEqual(response.status_code, 422)

        invalid_range = self.client.get(
            "/api/analytics/recent-events",
            params={"date_from": "2026-05-04", "date_to": "2026-05-03"},
        )
        self.assertEqual(invalid_range.status_code, 422)

        page = self.client.get("/dashboard")
        for marker in (
            'id="recent-events-panel"',
            'id="recent-events-filter"',
            'id="recent-events-limit"',
            'id="recent-events-body"',
            'id="recent-events-loading"',
            'id="recent-events-empty"',
            'id="recent-events-error"',
        ):
            self.assertIn(marker, page.text)
        for label in (
            "Data i godzina (UTC)",
            "Rodzaj zdarzenia",
            "Strona",
            "Szczegóły",
        ):
            self.assertIn(label, page.text)
        self.assertNotIn("session_token", page.text)


if __name__ == "__main__":
    unittest.main()
