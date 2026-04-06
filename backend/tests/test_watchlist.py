from fastapi.testclient import TestClient
from sqlalchemy import text
from decimal import Decimal
from datetime import UTC, datetime, timedelta

from snipebot.adapters.sites.base import AdapterCheckResult, ParsedProductData
from snipebot.api import watchlist as watchlist_api
from snipebot.main import app
from snipebot.persistence.db import get_engine, init_db


def _reset_watch_items() -> None:
    init_db()
    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM alert_events"))
        connection.execute(text("DELETE FROM price_checks"))
        connection.execute(text("DELETE FROM watch_items"))


def test_watchlist_rejects_malformed_url() -> None:
    _reset_watch_items()
    client = TestClient(app)

    response = client.post("/watchlist", json={"url": "notaurl"})

    assert response.status_code == 422


def test_watchlist_rejects_non_http_scheme() -> None:
    _reset_watch_items()
    client = TestClient(app)

    response = client.post("/watchlist", json={"url": "ftp://example.com/product"})

    assert response.status_code == 422


def test_watchlist_create_and_list() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen?utm_source=newsletter",
            "custom_label": "Hema deal",
            "target_price": 19.99,
        },
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["operation"] == "created"
    assert payload["item"]["site_key"] == "hema"
    assert payload["item"]["active"] is True
    assert payload["item"]["last_status"] == "pending"

    list_response = client.get("/watchlist")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["custom_label"] == "Hema deal"
    assert items[0]["target_price"] == 19.99
    assert items[0]["current_price"] is None
    assert items[0]["last_checked_at"] is None


def test_watchlist_upserts_by_normalized_url() -> None:
    _reset_watch_items()
    client = TestClient(app)

    first = client.post(
        "/watchlist",
        json={
            "url": "https://www.amazon.nl/dp/B0123?utm_source=abc",
            "custom_label": "first",
        },
    )
    assert first.status_code == 200
    assert first.json()["operation"] == "created"

    second = client.post(
        "/watchlist",
        json={
            "url": "https://amazon.nl/dp/B0123",
            "custom_label": "updated label",
            "target_price": 49.5,
        },
    )
    assert second.status_code == 200
    assert second.json()["operation"] == "updated"
    assert second.json()["item"]["site_key"] == "amazon_nl"

    list_response = client.get("/watchlist")
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["custom_label"] == "updated label"
    assert items[0]["target_price"] == 49.5


def test_watchlist_create_read_update_deactivate_flow() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.aliexpress.com/item/123.html",
            "custom_label": "initial",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["item"]
    assert created["active"] is True

    read_response = client.get("/watchlist")
    assert read_response.status_code == 200
    listed = read_response.json()["items"]
    assert len(listed) == 1
    assert listed[0]["custom_label"] == "initial"
    assert listed[0]["site_key"] == "aliexpress"

    update_response = client.post(
        "/watchlist",
        json={
            "url": "https://aliexpress.com/item/123.html?utm_source=email",
            "custom_label": "updated",
            "target_price": 17.25,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["operation"] == "updated"

    item_id = update_response.json()["item"]["id"]
    deactivate_response = client.patch(f"/watchlist/{item_id}/deactivate")
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["active"] is False

    final_read = client.get("/watchlist")
    assert final_read.status_code == 200
    final_items = final_read.json()["items"]
    assert len(final_items) == 1
    assert final_items[0]["custom_label"] == "updated"
    assert final_items[0]["target_price"] == 17.25
    assert final_items[0]["active"] is False


def test_watchlist_preview_returns_product_metadata(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)

    class _FakeAdapter:
        site_key = "amazon_nl"

        def check(
            self, url: str, *, allow_playwright_fallback: bool
        ) -> AdapterCheckResult:
            assert "amazon.nl" in url
            return AdapterCheckResult(
                ok=True,
                status="ok",
                data=ParsedProductData(
                    title="Test Headphones",
                    current_price=Decimal("19.99"),
                    currency="EUR",
                    availability="in_stock",
                ),
            )

    monkeypatch.setattr(watchlist_api, "get_adapter", lambda site_key: _FakeAdapter())

    response = client.get(
        "/watchlist/preview", params={"url": "https://www.amazon.nl/dp/B0123"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["site_key"] == "amazon_nl"
    assert payload["title"] == "Test Headphones"
    assert payload["current_price"] == 19.99
    assert payload["currency"] == "EUR"
    assert payload["suggested_label"] == "Test Headphones"


def test_watchlist_preview_returns_parse_error_details(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)

    class _FailingAdapter:
        site_key = "hema"

        def check(
            self, url: str, *, allow_playwright_fallback: bool
        ) -> AdapterCheckResult:
            assert "hema.nl" in url
            return AdapterCheckResult(
                ok=False,
                status="parse_error",
                error_kind="parse_error",
                error_message="Could not parse product price",
            )

    monkeypatch.setattr(
        watchlist_api, "get_adapter", lambda site_key: _FailingAdapter()
    )

    response = client.get(
        "/watchlist/preview",
        params={"url": "https://www.hema.nl/heren/herenkleding/shirts/example.html"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Preview failed: Could not parse product price"


def test_watch_item_history_returns_series_and_summary() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen/lamp",
            "custom_label": "History Lamp",
        },
    )
    assert create_response.status_code == 200
    item_id = create_response.json()["item"]["id"]

    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO price_checks (watch_item_id, adapter_key, status, current_price, currency, availability, used_fallback)
                VALUES (:item_id, 'hema', 'ok', 30.00, 'EUR', 'in_stock', 0),
                       (:item_id, 'hema', 'ok', 25.00, 'EUR', 'in_stock', 0),
                       (:item_id, 'hema', 'ok', 27.50, 'EUR', 'in_stock', 0)
                """
            ),
            {"item_id": item_id},
        )

    response = client.get(f"/watchlist/{item_id}/history", params={"days": 30})

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_id"] == item_id
    assert payload["checks_count"] == 3
    assert payload["latest_price"] == 27.5
    assert payload["lowest_price"] == 25.0
    assert payload["highest_price"] == 30.0
    assert len(payload["series"]) == 3


def test_watch_item_detail_includes_lows_and_patch_updates_notes() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen/lamp-2",
            "custom_label": "Detail Lamp",
        },
    )
    assert create_response.status_code == 200
    item_id = create_response.json()["item"]["id"]

    now = datetime.now(UTC)
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO price_checks (watch_item_id, checked_at, adapter_key, status, current_price, currency, availability, used_fallback)
                VALUES (:item_id, :d40, 'hema', 'ok', 30.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d20, 'hema', 'ok', 20.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d3, 'hema', 'ok', 25.00, 'EUR', 'in_stock', 0)
                """
            ),
            {
                "item_id": item_id,
                "d40": now - timedelta(days=40),
                "d20": now - timedelta(days=20),
                "d3": now - timedelta(days=3),
            },
        )

    detail_response = client.get(f"/watchlist/{item_id}")
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["item"]["custom_label"] == "Detail Lamp"
    assert payload["lows"]["low_7d"] == 25.0
    assert payload["lows"]["low_30d"] == 20.0
    assert payload["lows"]["all_time_low"] == 20.0

    patch_response = client.patch(
        f"/watchlist/{item_id}",
        json={"custom_label": "Updated Lamp", "notes": "Watch weekend deals"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["custom_label"] == "Updated Lamp"
    assert patch_response.json()["notes"] == "Watch weekend deals"

    detail_after_patch = client.get(f"/watchlist/{item_id}")
    assert detail_after_patch.status_code == 200
    assert detail_after_patch.json()["item"]["notes"] == "Watch weekend deals"


def test_watch_item_check_now_and_alert_history() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen/lamp-3",
            "custom_label": "Alert Lamp",
            "target_price": 29.99,
        },
    )
    assert create_response.status_code == 200
    item_id = create_response.json()["item"]["id"]

    now = datetime.now(UTC)
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO price_checks (watch_item_id, checked_at, adapter_key, status, current_price, currency, availability, used_fallback)
                VALUES (:item_id, :checked_at, 'hema', 'ok', 27.50, 'EUR', 'in_stock', 0)
                """
            ),
            {"item_id": item_id, "checked_at": now - timedelta(hours=1)},
        )
        check_id = connection.execute(
            text(
                "SELECT id FROM price_checks WHERE watch_item_id = :item_id ORDER BY id DESC LIMIT 1"
            ),
            {"item_id": item_id},
        ).scalar_one()

        connection.execute(
            text(
                """
                INSERT INTO alert_events (
                    watch_item_id, price_check_id, alert_kind, dedup_key, channel,
                    delivery_status, sent_at, label_or_title, site_key, product_url,
                    old_price, new_price, target_price, message_text, error_message
                )
                VALUES (
                    :item_id, :check_id, 'target_reached', 'k1', 'telegram',
                    'sent', :sent_at, 'Alert Lamp', 'hema', 'https://hema.nl/p/1',
                    30.00, 27.50, 29.99, 'message', NULL
                )
                """
            ),
            {
                "item_id": item_id,
                "check_id": check_id,
                "sent_at": now,
            },
        )

    check_now_response = client.post(f"/watchlist/{item_id}/check-now")
    assert check_now_response.status_code == 200
    assert check_now_response.json()["status"] == "queued_for_next_worker_tick"

    alert_history_response = client.get(f"/watchlist/{item_id}/alerts")
    assert alert_history_response.status_code == 200
    history_payload = alert_history_response.json()
    assert history_payload["item_id"] == item_id
    assert len(history_payload["events"]) == 1
    assert history_payload["events"][0]["alert_kind"] == "target_reached"
    assert history_payload["events"][0]["delivery_status"] == "sent"
