import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from marktplaats_fakes import (
    SEARCH_URL,
    CollectingNotifier,
    FakeFetcher,
    listing,
    search_payload,
)
from snipebot.adapters.marketplaces.marktplaats import MarktplaatsClient, MarktplaatsError
from snipebot.api.searches import get_marktplaats_client
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_searches import (
    create_search,
    format_euro,
    run_due_marketplace_searches,
)
from snipebot.main import app
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import (
    AppSetting,
    MarketplaceAlertEvent,
    MarketplaceListing,
    MarketplaceSearch,
)


def _reset_tables() -> None:
    init_db()
    with get_engine().begin() as connection:
        for table in (
            "marketplace_alert_events",
            "marketplace_listing_prices",
            "marketplace_listings",
            "marketplace_searches",
            "app_settings",
        ):
            connection.exec_driver_sql(f"DELETE FROM {table}")


def _enable_alerts() -> None:
    with get_session_factory()() as session:
        session.add_all(
            [
                AppSetting(key="notifications_enabled", value="true"),
                AppSetting(key="telegram_enabled", value="true"),
            ]
        )
        session.commit()


def _create(fetcher: FakeFetcher, **kwargs) -> int:
    with get_session_factory()() as session:
        search = create_search(
            session,
            MarktplaatsClient(fetch=fetcher),
            owner_id="local",
            name=kwargs.get("name", "Golf"),
            url=kwargs.get("url", SEARCH_URL),
            exclude_keywords=kwargs.get("exclude_keywords", []),
            seller_type=kwargs.get("seller_type", "all"),
        )
        return search.id


def _run(fetcher: FakeFetcher, notifier: CollectingNotifier, payload=None) -> None:
    if payload is not None:
        fetcher.payloads.append(payload)
    with get_session_factory()() as session:
        session.query(MarketplaceSearch).update(
            {MarketplaceSearch.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(
            session,
            get_settings(),
            client=MarktplaatsClient(fetch=fetcher),
            notifier=notifier,
        )


def _listings() -> list[MarketplaceListing]:
    with get_session_factory()() as session:
        return list(session.scalars(select(MarketplaceListing).order_by(MarketplaceListing.item_id)))


def test_baseline_is_silent_then_new_listing_alerts_once() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    baseline = search_payload([listing(200), listing(100)], total=500)
    _run(fetcher, notifier, baseline)
    assert notifier.messages == []
    assert all(row.from_baseline for row in _listings())

    with_new = search_payload([listing(300), listing(200), listing(100)], total=501)
    _run(fetcher, notifier, with_new)
    _run(fetcher, notifier, with_new)

    assert len(notifier.messages) == 1
    message = notifier.messages[0]
    assert message.title == "🆕 Nieuwe advertentie — Golf"
    assert "Volkswagen Golf 300" in message.body
    assert "💶 € 15.000" in message.body
    assert "🚗 2021 · 64.500 km · Benzine · Automaat" in message.body
    assert "📍 Almelo (12 km)" in message.body
    assert message.body.endswith("/v/auto-s/volkswagen/m300-volkswagen-golf")
    assert message.photo_url == "https://images.example.test/m300_85.jpg"

    with get_session_factory()() as session:
        events = session.scalars(select(MarketplaceAlertEvent)).all()
        search = session.scalars(select(MarketplaceSearch)).one()
    assert [(event.alert_kind, event.delivery_status) for event in events] == [
        ("new_listing", "sent")
    ]
    assert search.id_watermark == 300
    assert search.last_status == "ok"


def test_bumped_older_listing_is_not_reported_as_new() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(300), listing(200)], total=5000))
    # m150 is an older ad that was bumped back to the top of the results.
    _run(fetcher, notifier, search_payload([listing(150), listing(300), listing(200)], total=5000))

    assert notifier.messages == []
    rows = {row.item_id: row for row in _listings()}
    assert rows["m150"].from_baseline is False


def test_older_listing_entering_a_fully_covered_search_alerts() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(300), listing(200)]))
    _run(fetcher, notifier, search_payload([listing(300), listing(200), listing(150)]))

    assert len(notifier.messages) == 1
    assert "Volkswagen Golf 150" in notifier.messages[0].body


def test_price_drop_alerts_once_per_drop_and_records_history() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(100, price_cents=2250000)]))
    _run(fetcher, notifier, search_payload([listing(100, price_cents=2100000)]))
    _run(fetcher, notifier, search_payload([listing(100, price_cents=2100000)]))
    _run(fetcher, notifier, search_payload([listing(100, price_cents=2200000)]))

    assert len(notifier.messages) == 1
    assert notifier.messages[0].title == "📉 Prijsdaling — Golf"
    assert "💶 € 22.500 → € 21.000 (−€ 1.500)" in notifier.messages[0].body

    with get_session_factory()() as session:
        row = session.scalars(select(MarketplaceListing)).one()
        prices = [point.price for point in row.prices]
    assert prices == [Decimal("22500.00"), Decimal("21000.00"), Decimal("22000.00")]


def test_exclude_keywords_filter_title_and_description() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher, exclude_keywords=["Schade", " export "])

    _run(fetcher, notifier, search_payload([listing(100)]))
    _run(
        fetcher,
        notifier,
        search_payload(
            [
                listing(400, title="Golf met SCHADE"),
                listing(300, description="Geschikt voor export"),
                listing(200),
                listing(100),
            ]
        ),
    )

    assert len(notifier.messages) == 1
    assert "Volkswagen Golf 200" in notifier.messages[0].body
    assert [row.item_id for row in _listings()] == ["m100", "m200"]


def test_alerts_disabled_still_records_listings() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(100)]))
    _run(fetcher, notifier, search_payload([listing(200), listing(100)]))

    assert notifier.messages == []
    assert [row.item_id for row in _listings()] == ["m100", "m200"]


def test_failed_check_backs_off_without_alerting() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    fetcher.error = MarktplaatsError("blocked", "Marktplaats returned HTTP 429")
    _run(fetcher, notifier)

    with get_session_factory()() as session:
        search = session.scalars(select(MarketplaceSearch)).one()
    assert search.last_status == "blocked"
    assert search.consecutive_failure_count == 1
    assert search.baseline_done is False
    assert search.next_check_at.replace(tzinfo=UTC) > datetime.now(UTC)
    assert notifier.messages == []


def test_listings_missing_from_complete_results_are_marked_gone() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(200), listing(100)]))
    _run(fetcher, notifier, search_payload([listing(200)]))

    rows = {row.item_id: row for row in _listings()}
    assert rows["m100"].gone_at is not None
    assert rows["m200"].gone_at is None


def test_alert_flood_is_capped_with_summary() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(fetcher, notifier, search_payload([listing(100)]))
    _run(fetcher, notifier, search_payload([listing(1000 + n) for n in range(12)] + [listing(100)]))

    assert len(notifier.messages) == 11
    assert notifier.messages[-1].body == "+2 meer nieuwe meldingen; bekijk ze in SnipeBot."


def test_format_euro() -> None:
    assert format_euro(Decimal("21000")) == "€ 21.000"
    assert format_euro(Decimal("1234.5")) == "€ 1.234,50"


def _api_client(fetcher: FakeFetcher) -> TestClient:
    app.dependency_overrides[get_marktplaats_client] = lambda: MarktplaatsClient(fetch=fetcher)
    return TestClient(app)


def test_api_preview_create_list_and_listings() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    fetcher.default_payload = search_payload([listing(200), listing(100)], total=86)
    client = _api_client(fetcher)
    try:
        preview = client.post("/searches/preview", json={"url": SEARCH_URL, "seller_type": "private"})
        assert preview.status_code == 200
        body = preview.json()
        assert body["total_count"] == 86
        assert "Adverteerder: Particulier" in body["description"]
        assert "Prijs: t/m € 25.000" in body["description"]
        assert [item["item_id"] for item in body["sample"]] == ["m200", "m100"]

        created = client.post(
            "/searches",
            json={
                "name": "Golf GTI",
                "url": SEARCH_URL,
                "exclude_keywords": ["Schade", "schade", ""],
                "seller_type": "private",
            },
        )
        assert created.status_code == 201
        search = created.json()
        assert search["exclude_keywords"] == ["schade"]
        assert search["seller_type"] == "private"
        assert search["baseline_done"] is False

        with get_session_factory()() as session:
            stored = session.get(MarketplaceSearch, search["id"])
            assert 10898 in json.loads(stored.query_json)["attribute_ids"]

        _run(fetcher, CollectingNotifier())

        listed = client.get("/searches").json()["items"]
        assert [(item["name"], item["listing_count"], item["new_listing_count"]) for item in listed] == [
            ("Golf GTI", 2, 0)
        ]

        listings = client.get(f"/searches/{search['id']}/listings").json()["items"]
        assert listings[0]["seller_type"] == "private"
        assert listings[0]["attributes"]["fuel"] == "Benzine"
        assert listings[0]["distance_km"] == 12
        assert listings[0]["price_history"][0]["price"] == 15000.0
        assert listings[0]["is_new"] is False
    finally:
        app.dependency_overrides.clear()


def test_api_patch_filters_rebaselines_and_delete() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    fetcher.default_payload = search_payload([listing(100)])
    client = _api_client(fetcher)
    try:
        search_id = client.post("/searches", json={"name": "Golf", "url": SEARCH_URL}).json()["id"]
        _run(fetcher, CollectingNotifier())

        renamed = client.patch(f"/searches/{search_id}", json={"name": "Golf 8"}).json()
        assert renamed["name"] == "Golf 8"
        assert renamed["baseline_done"] is True

        changed = client.patch(
            f"/searches/{search_id}", json={"seller_type": "business", "active": False}
        ).json()
        assert changed["seller_type"] == "business"
        assert changed["baseline_done"] is False
        assert changed["active"] is False
        assert "Adverteerder: Bedrijf" in changed["description"]

        assert client.post(f"/searches/{search_id}/check-now").status_code == 200
        assert client.delete(f"/searches/{search_id}").status_code == 204
        assert client.get(f"/searches/{search_id}").status_code == 404
        assert _listings() == []
    finally:
        app.dependency_overrides.clear()


def test_api_rejects_non_marktplaats_url() -> None:
    _reset_tables()
    client = _api_client(FakeFetcher())
    try:
        response = client.post("/searches/preview", json={"url": "https://www.example.com/l/x/"})
        assert response.status_code == 422
        response = client.post(
            "/searches", json={"name": "x", "url": "https://www.marktplaats.nl/v/auto-s/m1"}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
