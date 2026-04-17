from fastapi.testclient import TestClient
from sqlalchemy import text
from decimal import Decimal
from datetime import UTC, datetime, timedelta

from snipebot.adapters.sites.base import AdapterCheckResult, ParsedProductData
from snipebot.api import watchlist as watchlist_api
from snipebot.core.config import get_settings
from snipebot.domain.price_checks import run_due_price_checks
from snipebot.main import app
from snipebot.persistence.db import get_engine, init_db


def _reset_watch_items() -> None:
    init_db()
    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM app_settings"))
        connection.execute(text("DELETE FROM alert_events"))
        connection.execute(text("DELETE FROM price_checks"))
        connection.execute(text("DELETE FROM watch_item_tag_links"))
        connection.execute(text("DELETE FROM watch_item_tags"))
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
                    image_url="https://images.example.test/headphones.jpg",
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
    assert payload["image_url"] == "https://images.example.test/headphones.jpg"
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


def test_watch_item_history_supports_more_than_one_year_window() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen/lamp-long-history",
            "custom_label": "Long History Lamp",
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
                VALUES (:item_id, :d730, 'hema', 'ok', 45.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d400, 'hema', 'ok', 39.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d20, 'hema', 'ok', 35.50, 'EUR', 'in_stock', 0)
                """
            ),
            {
                "item_id": item_id,
                "d730": now - timedelta(days=730),
                "d400": now - timedelta(days=400),
                "d20": now - timedelta(days=20),
            },
        )

    response = client.get(f"/watchlist/{item_id}/history", params={"days": 731})

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_id"] == item_id
    assert payload["checks_count"] == 3
    assert payload["lowest_price"] == 35.5
    assert payload["highest_price"] == 45.0
    assert len(payload["series"]) == 3


def test_watch_item_history_auto_resolution_uses_daily_aggregation_for_long_windows() -> (
    None
):
    _reset_watch_items()
    client = TestClient(app)

    create_response = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/wonen-slapen/lamp-auto-resolution",
            "custom_label": "Auto Resolution Lamp",
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
                VALUES (:item_id, :d100a, 'hema', 'ok', 10.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d100b, 'hema', 'ok', 12.00, 'EUR', 'in_stock', 0),
                       (:item_id, :d20, 'hema', 'ok', 8.00, 'EUR', 'in_stock', 0)
                """
            ),
            {
                "item_id": item_id,
                "d100a": now - timedelta(days=100, hours=1),
                "d100b": now - timedelta(days=100, hours=2),
                "d20": now - timedelta(days=20),
            },
        )

    response = client.get(f"/watchlist/{item_id}/history", params={"days": 180})

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks_count"] == 2
    assert payload["lowest_price"] == 8.0
    assert payload["highest_price"] == 11.0
    assert payload["latest_price"] == 8.0
    assert len(payload["series"]) == 2


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


def test_watchlist_supports_filters_and_pagination() -> None:
    _reset_watch_items()
    client = TestClient(app)

    first = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/p/alpha",
            "custom_label": "Alpha",
            "target_price": 10,
        },
    )
    second = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/p/beta",
            "custom_label": "Beta",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    beta_id = second.json()["item"]["id"]
    deactivate = client.patch(f"/watchlist/{beta_id}/deactivate")
    assert deactivate.status_code == 200

    filtered = client.get(
        "/watchlist",
        params={"active": "false", "has_target": "false", "q": "beta"},
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["custom_label"] == "Beta"

    paged = client.get(
        "/watchlist", params={"limit": 1, "offset": 0, "sort": "updated_desc"}
    )
    assert paged.status_code == 200
    paged_payload = paged.json()
    assert paged_payload["total"] == 2
    assert paged_payload["limit"] == 1
    assert paged_payload["offset"] == 0
    assert len(paged_payload["items"]) == 1


def test_watchlist_supports_column_sort_keys() -> None:
    _reset_watch_items()
    client = TestClient(app)

    alpha = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/sort-alpha", "custom_label": "Zulu"},
    )
    beta = client.post(
        "/watchlist",
        json={"url": "https://www.amazon.nl/dp/B0123", "custom_label": "Alpha"},
    )
    gamma = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/sort-gamma", "custom_label": "Mike"},
    )

    assert alpha.status_code == 200
    assert beta.status_code == 200
    assert gamma.status_code == 200

    by_label_asc = client.get("/watchlist", params={"sort": "label_asc"})
    assert by_label_asc.status_code == 200
    labels_asc = [item["custom_label"] for item in by_label_asc.json()["items"]]
    assert labels_asc[:3] == ["Alpha", "Mike", "Zulu"]

    by_label_desc = client.get("/watchlist", params={"sort": "label_desc"})
    assert by_label_desc.status_code == 200
    labels_desc = [item["custom_label"] for item in by_label_desc.json()["items"]]
    assert labels_desc[:3] == ["Zulu", "Mike", "Alpha"]

    by_site_asc = client.get("/watchlist", params={"sort": "site_asc"})
    assert by_site_asc.status_code == 200
    sites_asc = [item["site_key"] for item in by_site_asc.json()["items"]]
    assert sites_asc[0] == "amazon_nl"

    by_site_desc = client.get("/watchlist", params={"sort": "site_desc"})
    assert by_site_desc.status_code == 200
    sites_desc = [item["site_key"] for item in by_site_desc.json()["items"]]
    assert sites_desc[0] == "hema"


def test_watchlist_bulk_archive_and_restore_flow() -> None:
    _reset_watch_items()
    client = TestClient(app)

    first = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/p/archive-a",
            "custom_label": "Archive A",
        },
    )
    second = client.post(
        "/watchlist",
        json={
            "url": "https://www.hema.nl/p/archive-b",
            "custom_label": "Archive B",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["item"]["id"]
    second_id = second.json()["item"]["id"]

    bulk_archive = client.post(
        "/watchlist/bulk",
        json={
            "item_ids": [first_id, second_id],
            "action": "archive",
        },
    )
    assert bulk_archive.status_code == 200
    archive_payload = bulk_archive.json()
    assert archive_payload["updated"] == 2
    assert archive_payload["failed"] == []

    visible = client.get("/watchlist")
    assert visible.status_code == 200
    assert visible.json()["items"] == []

    archived = client.get(
        "/watchlist", params={"include_archived": "true", "archived_only": "true"}
    )
    assert archived.status_code == 200
    archived_items = archived.json()["items"]
    assert len(archived_items) == 2
    assert all(item["archived_at"] is not None for item in archived_items)

    restored = client.post(f"/watchlist/{first_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None

    visible_after_restore = client.get("/watchlist")
    assert visible_after_restore.status_code == 200
    visible_items = visible_after_restore.json()["items"]
    assert len(visible_items) == 1
    assert visible_items[0]["id"] == first_id


def test_watchlist_tags_create_assign_and_filter() -> None:
    _reset_watch_items()
    client = TestClient(app)

    create_item = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/tags-1", "custom_label": "Tagged item"},
    )
    assert create_item.status_code == 200
    item_id = create_item.json()["item"]["id"]

    create_tag = client.post("/watchlist/tags", json={"name": "Deals"})
    assert create_tag.status_code == 200
    assert create_tag.json()["name"] == "Deals"

    assign = client.patch(
        f"/watchlist/{item_id}/tags", json={"tags": ["Deals", "Weekend"]}
    )
    assert assign.status_code == 200
    assert assign.json()["tags"] == ["Deals", "Weekend"]

    tag_list = client.get("/watchlist/tags")
    assert tag_list.status_code == 200
    names = [entry["name"] for entry in tag_list.json()["tags"]]
    assert names == ["Deals", "Weekend"]

    filtered = client.get("/watchlist", params={"tag": "deals"})
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == item_id


def test_watchlist_import_dry_run_and_apply_and_export() -> None:
    _reset_watch_items()
    client = TestClient(app)

    dry_run = client.post(
        "/watchlist/import",
        params={"dry_run": "true"},
        json={
            "items": [
                {
                    "url": "https://www.hema.nl/p/import-a",
                    "custom_label": "Import A",
                    "target_price": 11.25,
                    "tags": ["Kitchen", "Deals"],
                },
                {
                    "url": "notaurl",
                    "custom_label": "Broken",
                },
            ]
        },
    )
    assert dry_run.status_code == 200
    dry_payload = dry_run.json()
    assert dry_payload["dry_run"] is True
    assert dry_payload["summary"]["created"] == 1
    assert dry_payload["summary"]["error"] == 1

    list_after_dry_run = client.get("/watchlist")
    assert list_after_dry_run.status_code == 200
    assert list_after_dry_run.json()["total"] == 0

    apply = client.post(
        "/watchlist/import",
        params={"dry_run": "false"},
        json={
            "items": [
                {
                    "url": "https://www.hema.nl/p/import-a",
                    "custom_label": "Import A",
                    "target_price": 11.25,
                    "tags": ["Kitchen", "Deals"],
                },
                {
                    "url": "https://www.hema.nl/p/import-a",
                    "custom_label": "Import A Updated",
                    "target_price": 10.50,
                    "tags": "Kitchen",
                },
            ]
        },
    )
    assert apply.status_code == 200
    apply_payload = apply.json()
    assert apply_payload["dry_run"] is False
    assert apply_payload["summary"]["created"] == 1
    assert apply_payload["summary"]["updated"] == 1

    list_after_apply = client.get("/watchlist")
    assert list_after_apply.status_code == 200
    list_payload = list_after_apply.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["custom_label"] == "Import A Updated"
    assert list_payload["items"][0]["tags"] == ["Kitchen"]

    export_json = client.get("/watchlist/export", params={"format": "json"})
    assert export_json.status_code == 200
    export_payload = export_json.json()
    assert export_payload["count"] == 1
    assert export_payload["items"][0]["tags"] == ["Kitchen"]

    export_csv = client.get("/watchlist/export", params={"format": "csv"})
    assert export_csv.status_code == 200
    assert "text/csv" in export_csv.headers["content-type"]
    assert "Import A Updated" in export_csv.text


def test_watchlist_owner_scoping_separates_data() -> None:
    _reset_watch_items()
    client = TestClient(app)

    local_item = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/local-item", "custom_label": "Local"},
    )
    assert local_item.status_code == 200

    alice_item = client.post(
        "/watchlist",
        headers={"X-Owner-Id": "alice"},
        json={"url": "https://www.hema.nl/p/alice-item", "custom_label": "Alice"},
    )
    assert alice_item.status_code == 200

    local_list = client.get("/watchlist")
    assert local_list.status_code == 200
    assert local_list.json()["total"] == 1
    assert local_list.json()["items"][0]["custom_label"] == "Local"

    alice_list = client.get("/watchlist", headers={"X-Owner-Id": "alice"})
    assert alice_list.status_code == 200
    assert alice_list.json()["total"] == 1
    assert alice_list.json()["items"][0]["custom_label"] == "Alice"


def test_watchlist_health_and_metrics_endpoint() -> None:
    _reset_watch_items()
    client = TestClient(app)

    created = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/health-item", "custom_label": "Health"},
    )
    assert created.status_code == 200

    health_response = client.get("/watchlist/health")
    assert health_response.status_code == 200
    payload = health_response.json()
    assert payload["owner_id"] == "local"
    assert payload["total"] == 1
    assert payload["active"] == 1
    assert payload["dead_lettered"] == 0

    metrics_response = client.get("/health/metrics")
    assert metrics_response.status_code == 200
    counters = metrics_response.json()["counters"]
    assert "api.watchlist.upsert" in counters
    assert counters["api.watchlist.health"] >= 1


def test_write_rate_limit_blocks_excess_requests() -> None:
    _reset_watch_items()
    client = TestClient(app)
    settings = get_settings()
    original_limit = settings.rate_limit_write_requests_per_minute
    original_window = settings.rate_limit_window_seconds

    settings.rate_limit_write_requests_per_minute = 2
    settings.rate_limit_window_seconds = 60
    try:
        headers = {"X-Owner-Id": "rate-limit-test-owner"}
        first = client.post("/watchlist/tags", headers=headers, json={"name": "rl-a"})
        second = client.post("/watchlist/tags", headers=headers, json={"name": "rl-b"})
        third = client.post("/watchlist/tags", headers=headers, json={"name": "rl-c"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
    finally:
        settings.rate_limit_write_requests_per_minute = original_limit
        settings.rate_limit_window_seconds = original_window


def test_price_checks_dead_letter_after_repeated_failures(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)
    created = client.post(
        "/watchlist",
        json={"url": "https://www.hema.nl/p/fail-item", "custom_label": "Fail item"},
    )
    assert created.status_code == 200
    item_id = created.json()["item"]["id"]

    class _FailingAdapter:
        site_key = "hema"

        def check(self, *_args, **_kwargs):
            return AdapterCheckResult(
                ok=False,
                status="fetch_error",
                error_kind="timeout",
                error_message="simulated timeout",
            )

    monkeypatch.setattr(
        "snipebot.domain.price_checks.get_adapter", lambda _site_key: _FailingAdapter()
    )

    settings = get_settings()
    original_threshold = settings.dead_letter_failure_threshold
    original_retry = settings.retry_interval_seconds
    original_backoff = settings.retry_backoff_multiplier
    original_max_retry = settings.retry_max_interval_seconds

    settings.dead_letter_failure_threshold = 2
    settings.retry_interval_seconds = 1
    settings.retry_backoff_multiplier = 2
    settings.retry_max_interval_seconds = 60
    try:
        from snipebot.persistence.db import get_session_factory

        session_factory = get_session_factory()
        for _ in range(2):
            with get_engine().begin() as connection:
                connection.execute(
                    text(
                        "UPDATE watch_items SET next_check_at = :due WHERE id = :item_id"
                    ),
                    {
                        "due": datetime.now(UTC) - timedelta(seconds=1),
                        "item_id": item_id,
                    },
                )
            with session_factory() as db_session:
                run_due_price_checks(db_session, settings)

        item_response = client.get(f"/watchlist/{item_id}")
        assert item_response.status_code == 200
        detail = item_response.json()["item"]
        assert detail["dead_lettered_at"] is not None
        assert detail["active"] is False
        assert detail["consecutive_failure_count"] >= 2
    finally:
        settings.dead_letter_failure_threshold = original_threshold
        settings.retry_interval_seconds = original_retry
        settings.retry_backoff_multiplier = original_backoff
        settings.retry_max_interval_seconds = original_max_retry


def test_settings_get_defaults_and_patch_persists() -> None:
    _reset_watch_items()
    client = TestClient(app)

    defaults = client.get("/settings")
    assert defaults.status_code == 200
    defaults_payload = defaults.json()
    runtime_defaults = get_settings()
    assert (
        defaults_payload["notifications_enabled"]
        is runtime_defaults.notifications_enabled
    )
    assert defaults_payload["telegram_enabled"] is runtime_defaults.telegram_enabled
    assert defaults_payload["telegram_bot_token"] == runtime_defaults.telegram_bot_token
    assert defaults_payload["telegram_chat_id"] == runtime_defaults.telegram_chat_id
    assert (
        defaults_payload["check_interval_seconds"]
        == runtime_defaults.check_interval_seconds
    )
    assert (
        defaults_payload["playwright_fallback_enabled"]
        is runtime_defaults.playwright_fallback_enabled
    )
    assert defaults_payload["playwright_fallback_adapters"] == [
        entry.strip()
        for entry in runtime_defaults.playwright_fallback_adapters.split(",")
        if entry.strip()
    ]
    assert defaults_payload["log_level"] == runtime_defaults.log_level.upper()

    patched = client.patch(
        "/settings",
        json={
            "notifications_enabled": True,
            "telegram_enabled": True,
            "telegram_bot_token": "token-from-ui",
            "telegram_chat_id": "chat-from-ui",
            "check_interval_seconds": 900,
            "playwright_fallback_enabled": True,
            "playwright_fallback_adapters": ["amazon_nl", "hema"],
            "log_level": "debug",
        },
    )
    assert patched.status_code == 200
    patched_payload = patched.json()
    assert patched_payload["notifications_enabled"] is True
    assert patched_payload["telegram_enabled"] is True
    assert patched_payload["telegram_bot_token"] == "token-from-ui"
    assert patched_payload["telegram_chat_id"] == "chat-from-ui"
    assert patched_payload["check_interval_seconds"] == 900
    assert patched_payload["playwright_fallback_enabled"] is True
    assert patched_payload["playwright_fallback_adapters"] == ["amazon_nl", "hema"]
    assert patched_payload["log_level"] == "DEBUG"

    persisted = client.get("/settings")
    assert persisted.status_code == 200
    assert persisted.json() == patched_payload


def test_settings_patch_rejects_invalid_log_level() -> None:
    _reset_watch_items()
    client = TestClient(app)

    response = client.patch("/settings", json={"log_level": "TRACE"})

    assert response.status_code == 422
    assert "log_level must be one of" in response.json()["detail"]


def test_settings_patch_rejects_bot_id_as_chat_id() -> None:
    _reset_watch_items()
    client = TestClient(app)

    response = client.patch(
        "/settings",
        json={
            "telegram_bot_token": "123456:ABC",
            "telegram_chat_id": "123456",
        },
    )

    assert response.status_code == 422
    assert "telegram_chat_id may not be the bot id" in response.json()["detail"]


def test_settings_test_telegram_endpoint_reports_success(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)

    captured: dict[str, object] = {}

    class _Notifier:
        def send(self, message):
            captured["text"] = message.text

            class _Result:
                ok = True
                provider_message_id = "m-123"
                error = None

            return _Result()

    def _fake_build_notifier(_settings, **kwargs):
        captured.update(kwargs)
        return _Notifier()

    monkeypatch.setattr("snipebot.api.settings.build_notifier", _fake_build_notifier)

    response = client.post(
        "/settings/test-telegram",
        json={
            "notifications_enabled": True,
            "telegram_enabled": True,
            "telegram_bot_token": "token-ui",
            "telegram_chat_id": "chat-ui",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider_message_id"] == "m-123"
    assert captured["notifications_enabled"] is True
    assert captured["telegram_enabled"] is True
    assert captured["telegram_bot_token"] == "token-ui"
    assert captured["telegram_chat_id"] == "chat-ui"
    assert "SnipeBot test" in str(captured["text"])


def test_settings_test_telegram_endpoint_reports_error(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)

    class _Notifier:
        def send(self, _message):
            class _Result:
                ok = False
                provider_message_id = None
                error = "notifications_disabled"

            return _Result()

    monkeypatch.setattr(
        "snipebot.api.settings.build_notifier",
        lambda _settings, **_kwargs: _Notifier(),
    )

    response = client.post(
        "/settings/test-telegram",
        json={
            "notifications_enabled": False,
            "telegram_enabled": True,
            "telegram_bot_token": "token-ui",
            "telegram_chat_id": "chat-ui",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["detail"] == "notifications_disabled"


def test_settings_test_telegram_endpoint_rejects_bot_id_as_chat_id(monkeypatch) -> None:
    _reset_watch_items()
    client = TestClient(app)

    called = {"value": False}

    class _Notifier:
        def send(self, _message):
            called["value"] = True

            class _Result:
                ok = True
                provider_message_id = "msg"
                error = None

            return _Result()

    monkeypatch.setattr(
        "snipebot.api.settings.build_notifier",
        lambda _settings, **_kwargs: _Notifier(),
    )

    response = client.post(
        "/settings/test-telegram",
        json={
            "telegram_bot_token": "123456:ABC",
            "telegram_chat_id": "123456",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "telegram_chat_id may not be the bot id" in payload["detail"]
    assert called["value"] is False
