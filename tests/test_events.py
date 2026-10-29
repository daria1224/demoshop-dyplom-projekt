import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

# Testy nie odczytują lokalnej konfiguracji ani nie łączą się z Neon.
with patch("dotenv.load_dotenv"):
    from backend import main


class EventEndpointTests(unittest.TestCase):
    NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        main.event_rate_limiter.clear()
        self.now_patch = patch.object(main, "utc_now", return_value=self.NOW)
        self.now_patch.start()
        self.addCleanup(self.now_patch.stop)
        self.save_patch = patch.object(main, "save_event")
        self.save_event = self.save_patch.start()
        self.addCleanup(self.save_patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def event(self, event_type, **metadata):
        return {
            "session_token": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": event_type,
            "page": "/products.html",
            "timestamp": self.NOW.isoformat(),
            **metadata,
        }

    def test_accepts_all_supported_event_types_and_metadata(self):
        cases = [
            self.event("page_view", title="Produkty — DemoShop"),
            self.event(
                "click",
                element="view_product_button",
                product_id="kubek-aurora",
                product_name="Kubek Aurora",
            ),
            self.event(
                "click",
                element="navigation_link",
                destination="cart.html",
            ),
            self.event("click", element="mobile_menu", open=True),
            self.event(
                "view_item",
                product_id="kubek-aurora",
                product_name="Kubek Aurora",
            ),
            self.event(
                "add_to_cart",
                product_id="kubek-aurora",
                product_name="Kubek Aurora",
                cart_count=2,
            ),
            self.event("form_submit", form="contact"),
        ]

        for payload in cases:
            with self.subTest(event_type=payload["event_type"]):
                response = self.client.post("/api/events", json=payload)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(self.save_event.call_count, len(cases))
        form_call = self.save_event.call_args_list[-1].kwargs
        self.assertEqual(form_call["metadata"], {"form": "contact"})

    def test_rejects_unknown_type_missing_fields_and_invalid_lengths(self):
        cases = [
            self.event("unknown", title="Test"),
            self.event("page_view"),
            self.event("click", element="x" * 101),
            self.event("page_view", title="x" * 201),
            {**self.event("page_view", title="Test"), "session_token": "x" * 129},
            {**self.event("page_view", title="Test"), "page": "/" + "x" * 512},
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/events", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": "Nieprawidłowe dane zdarzenia."})

        self.save_event.assert_not_called()

    def test_rejects_unapproved_or_sensitive_metadata_without_echoing_it(self):
        marker = "prywatna-tresc-formularza@example.com"
        cases = [
            self.event("form_submit", form="contact", message=marker),
            self.event("form_submit", form="contact", email=marker),
            self.event("click", element="navigation_link", title=marker),
            self.event("page_view", title="Test", product_name=marker),
        ]

        for payload in cases:
            with self.subTest(extra=set(payload) - {"session_token", "event_type", "page", "timestamp"}):
                response = self.client.post("/api/events", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(marker, response.text)

        self.save_event.assert_not_called()

    def test_timestamp_boundaries_timezone_and_invalid_values(self):
        for timestamp in (
            self.NOW - main.EVENT_TIMESTAMP_TOLERANCE,
            self.NOW + main.EVENT_TIMESTAMP_TOLERANCE,
            self.NOW.astimezone(timezone(timedelta(hours=5, minutes=30))),
        ):
            payload = self.event("page_view", title="Test")
            payload["timestamp"] = timestamp.isoformat()
            response = self.client.post("/api/events", json=payload)
            self.assertEqual(response.status_code, 200)

        normalized_call = self.save_event.call_args.kwargs
        self.assertEqual(normalized_call["created_at"].tzinfo, timezone.utc)

        invalid = [
            (self.NOW - main.EVENT_TIMESTAMP_TOLERANCE - timedelta(microseconds=1)).isoformat(),
            (self.NOW + main.EVENT_TIMESTAMP_TOLERANCE + timedelta(microseconds=1)).isoformat(),
            "2026-10-29T12:00:00",
            "nie-data",
        ]
        for timestamp in invalid:
            payload = self.event("page_view", title="Test")
            payload["timestamp"] = timestamp
            response = self.client.post("/api/events", json=payload)
            self.assertEqual(response.status_code, 422)

    def test_request_size_limit(self):
        valid = self.event("page_view", title="Test")
        response = self.client.post("/api/events", json=valid)
        self.assertEqual(response.status_code, 200)

        oversized = json.dumps({"padding": "x" * main.EVENT_REQUEST_MAX_BYTES})
        response = self.client.post(
            "/api/events",
            content=oversized,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)

    def test_rate_limit_allows_normal_burst_and_rejects_excess(self):
        payload = self.event("page_view", title="Test")
        with patch.object(main.time, "monotonic", return_value=1000.0):
            for _ in range(main.EVENT_RATE_LIMIT):
                response = self.client.post("/api/events", json=payload)
                self.assertEqual(response.status_code, 200)
            response = self.client.post("/api/events", json=payload)
            self.assertEqual(response.status_code, 429)
            self.assertIn("retry-after", response.headers)

        with patch.object(
            main.time,
            "monotonic",
            return_value=1000.0 + main.EVENT_RATE_WINDOW_SECONDS + 0.1,
        ):
            response = self.client.post("/api/events", json=payload)
            self.assertEqual(response.status_code, 200)

    def test_limiter_bounds_client_state(self):
        limiter = main.EventRateLimiter(limit=2, window_seconds=60, max_clients=2)
        self.assertIsNone(limiter.check("client-a", now=1))
        self.assertIsNone(limiter.check("client-b", now=1))
        self.assertIsNone(limiter.check("client-c", now=1))
        self.assertEqual(list(limiter._requests), ["client-b", "client-c"])
        self.assertIsNone(limiter.check("client-d", now=62))
        self.assertEqual(list(limiter._requests), ["client-d"])


if __name__ == "__main__":
    unittest.main()
