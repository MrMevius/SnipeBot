import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from marktplaats_fakes import (
    GOLF_QUERY,
    CollectingNotifier,
    FakeFetcher,
    listing,
    search_payload,
)
from snipebot.adapters.marketplaces.base import SearchFilters
from snipebot.adapters.marketplaces.marktplaats import (
    MarktplaatsAdapter,
    MarktplaatsClient,
    MarktplaatsError,
)
from snipebot.api.searches import get_platform_adapters
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_searches import (
    cheapest_listing,
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
    MarketplaceSearchSource,
)

GOLF_FILTERS = {
    "make": "Volkswagen",
    "model": "Golf",
    "year_min": 2018,
    "price_max": 25000,
    "mileage_max": 100000,
}


def _reset_tables() -> None:
    init_db()
    with get_engine().begin() as connection:
        for table in (
            "marketplace_item_prices",
            "marketplace_item_images",
            "marketplace_item_versions",
            "marketplace_items",
            "marketplace_alert_events",
            "marketplace_listing_prices",
            "marketplace_listings",
            "marketplace_search_sources",
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


def _adapters(fetcher: FakeFetcher) -> dict:
    return {"marktplaats": MarktplaatsAdapter(MarktplaatsClient(fetch=fetcher))}


def _create(fetcher: FakeFetcher, **kwargs) -> int:
    with get_session_factory()() as session:
        search = create_search(
            session,
            _adapters(fetcher),
            owner_id="local",
            name=kwargs.get("name", "Golf"),
            filters=SearchFilters(**GOLF_FILTERS),
            platforms=["marktplaats"],
            exclude_keywords=kwargs.get("exclude_keywords", []),
            seller_type=kwargs.get("seller_type", "all"),
            alert_max_price=kwargs.get("alert_max_price", Decimal("1000000")),
        )
        return search.id


def _run(fetcher: FakeFetcher, notifier: CollectingNotifier, payload=None) -> None:
    if payload is not None:
        fetcher.payloads.append(payload)
    with get_session_factory()() as session:
        session.query(MarketplaceSearchSource).update(
            {MarketplaceSearchSource.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(
            session,
            get_settings(),
            adapters=_adapters(fetcher),
            notifier=notifier,
        )


def _source() -> MarketplaceSearchSource:
    with get_session_factory()() as session:
        return session.scalars(select(MarketplaceSearchSource)).one()


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
    assert "📍 🇳🇱 Almelo · 12 km" in message.body
    assert message.body.endswith("/v/auto-s/volkswagen/m300-volkswagen-golf")
    assert message.photo_url == "https://images.example.test/m300_85.jpg"

    with get_session_factory()() as session:
        events = session.scalars(select(MarketplaceAlertEvent)).all()
    assert [(event.alert_kind, event.delivery_status) for event in events] == [
        ("new_listing", "sent")
    ]
    source = _source()
    assert source.id_watermark == 300
    assert source.last_status == "ok"


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


def test_alerts_respect_the_price_ceiling() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher, alert_max_price=Decimal("20000"))

    _run(fetcher, notifier, search_payload([listing(100, price_cents=2500000)]))
    # New listings: only the one at or below the ceiling alerts; no price, no alert.
    _run(
        fetcher,
        notifier,
        search_payload(
            [
                listing(300, price_cents=2000000),
                listing(250, price_cents=2100000),
                listing(240, price_cents=0),
                listing(100, price_cents=2500000),
            ]
        ),
    )
    assert [message.title for message in notifier.messages] == ["🆕 Nieuwe advertentie — Golf"]
    assert "Volkswagen Golf 300" in notifier.messages[0].body

    # Drops: above the ceiling stays silent; to and below the ceiling alert each time.
    notifier.messages.clear()
    for price_cents in (2200000, 1950000, 1900000):
        _run(fetcher, notifier, search_payload([listing(100, price_cents=price_cents)]))
    assert [message.body.splitlines()[1] for message in notifier.messages] == [
        "💶 € 22.000 → € 19.500 (−€ 2.500)",
        "💶 € 19.500 → € 19.000 (−€ 500)",
    ]


def test_search_without_ceiling_sends_no_alerts() -> None:
    _reset_tables()
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher, alert_max_price=None)

    _run(fetcher, notifier, search_payload([listing(100)]))
    _run(fetcher, notifier, search_payload([listing(200), listing(100, price_cents=100000)]))

    assert notifier.messages == []
    assert len(_listings()) == 2


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

    source = _source()
    assert source.last_status == "blocked"
    assert source.consecutive_failure_count == 1
    assert source.baseline_done is False
    assert source.next_check_at.replace(tzinfo=UTC) > datetime.now(UTC)
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


def test_cheapest_listing_skips_gone_and_unpriced_listings() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _create(fetcher)

    _run(
        fetcher,
        notifier,
        search_payload([listing(300, price_cents=0), listing(200, price_cents=900000), listing(100)]),
    )
    # m200 disappears from the complete result set and is marked gone.
    _run(fetcher, notifier, search_payload([listing(300, price_cents=0), listing(100)]))

    with get_session_factory()() as session:
        search = session.scalars(select(MarketplaceSearch)).one()
        cheapest = cheapest_listing(session, search)
    assert cheapest.item_id == "m100"


def test_format_euro() -> None:
    assert format_euro(Decimal("21000")) == "€ 21.000"
    assert format_euro(Decimal("1234.5")) == "€ 1.234,50"


def _api_client(fetcher: FakeFetcher) -> TestClient:
    app.dependency_overrides[get_platform_adapters] = lambda: _adapters(fetcher)
    return TestClient(app)


def test_api_platforms_makes_and_models() -> None:
    _reset_tables()
    client = _api_client(FakeFetcher())
    try:
        assert client.get("/searches/platforms").json()["items"] == [
            {"key": "marktplaats", "label": "Marktplaats"}
        ]
        makes = client.get("/searches/makes").json()
        assert makes["items"] == [
            {"label": "Tesla", "platforms": ["marktplaats"]},
            {"label": "Volkswagen", "platforms": ["marktplaats"]},
        ]
        models = client.get("/searches/models", params={"make": "volkswagen"}).json()
        assert models["items"] == [{"label": "Golf", "platforms": ["marktplaats"]}]
    finally:
        app.dependency_overrides.clear()


def test_api_preview_create_list_and_listings() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    fetcher.default_payload = search_payload(
        [listing(200), listing(100, price_cents=1400000)], total=86
    )
    client = _api_client(fetcher)
    try:
        preview = client.post(
            "/searches/preview",
            json={"filters": GOLF_FILTERS, "platforms": ["marktplaats"], "seller_type": "private"},
        )
        assert preview.status_code == 200
        body = preview.json()
        assert body["description"] == [
            "Auto: Volkswagen Golf",
            "Bouwjaar: vanaf 2018",
            "Prijs: t/m € 25.000",
            "Kilometerstand: t/m 100.000 km",
            "Verkoper: Particulier",
        ]
        [platform] = body["platforms"]
        assert platform["total_count"] == 86
        assert platform["error"] is None
        assert [item["item_id"] for item in platform["sample"]] == ["m200", "m100"]

        created = client.post(
            "/searches",
            json={
                "name": "Golf GTI",
                "filters": GOLF_FILTERS,
                "platforms": ["marktplaats"],
                "exclude_keywords": ["Schade", "schade", ""],
                "seller_type": "private",
                "alert_max_price": 25000,
            },
        )
        assert created.status_code == 201
        search = created.json()
        assert search["alert_max_price"] == 25000.0
        assert search["exclude_keywords"] == ["schade"]
        assert search["seller_type"] == "private"
        assert search["baseline_done"] is False
        assert search["filters"]["make"] == "Volkswagen"
        assert search["unknown_policy"] == "include"
        assert [item["marketplace"] for item in search["platforms"]] == ["marktplaats"]

        query = json.loads(_source().query_json)
        assert query["attribute_ids"] == [1260, 10882, 10898]

        _run(fetcher, CollectingNotifier())

        listed = client.get("/searches").json()["items"]
        assert [(item["name"], item["listing_count"], item["new_listing_count"]) for item in listed] == [
            ("Golf GTI", 2, 0)
        ]
        assert listed[0]["last_status"] == "ok"
        assert listed[0]["baseline_done"] is True
        assert listed[0]["cheapest"]["item_id"] == "m100"
        assert listed[0]["cheapest"]["marketplace"] == "marktplaats"
        assert listed[0]["cheapest"]["price"] == 14000.0

        listings = client.get(f"/searches/{search['id']}/listings").json()["items"]
        assert listings[0]["marketplace"] == "marktplaats"
        assert listings[0]["seller_type"] == "private"
        assert listings[0]["attributes"]["fuel"] == "Benzine"
        assert listings[0]["distance_km"] == 12
        assert listings[0]["price_history"][0]["price"] == 14000.0
        assert listings[0]["is_new"] is False
        assert listings[0]["unverified_filters"] == []
    finally:
        app.dependency_overrides.clear()


def test_api_listings_page_sort_and_day_counts() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    search_id = _create(fetcher)
    _run(fetcher, notifier, search_payload([listing(100), listing(200)]))
    _run(
        fetcher,
        notifier,
        search_payload(
            [
                listing(200),
                listing(300, title="Volkswagen Golf 4x4 met trekhaak", price_cents=1200000),
                listing(400, price_cents=900000),
            ]
        ),
    )
    client = _api_client(fetcher)
    try:
        search = client.get(f"/searches/{search_id}").json()
        assert (search["new_last_day_count"], search["gone_last_day_count"]) == (2, 1)

        params = {"include_gone": "false", "sort": "price", "direction": "asc", "page_size": 2}
        first = client.get(f"/searches/{search_id}/listings", params=params).json()
        assert (first["total"], first["page"], first["page_size"]) == (3, 1, 2)
        assert [item["item_id"] for item in first["items"]] == ["m400", "m300"]
        assert first["items"][1]["highlights"] == ["AWD", "Tow hitch"]
        assert first["items"][0]["highlights"] == []

        second = client.get(f"/searches/{search_id}/listings", params={**params, "page": 2}).json()
        assert [item["item_id"] for item in second["items"]] == ["m200"]

        everything = client.get(f"/searches/{search_id}/listings").json()
        assert everything["total"] == 4
        assert everything["page_size"] is None
        assert everything["items"][-1]["item_id"] == "m100"
    finally:
        app.dependency_overrides.clear()


def test_api_patch_filters_rebaselines_and_delete() -> None:
    _reset_tables()
    fetcher = FakeFetcher()
    fetcher.default_payload = search_payload([listing(100)])
    client = _api_client(fetcher)
    try:
        search_id = client.post(
            "/searches",
            json={"name": "Golf", "filters": GOLF_FILTERS, "platforms": ["marktplaats"]},
        ).json()["id"]
        _run(fetcher, CollectingNotifier())

        renamed = client.patch(f"/searches/{search_id}", json={"name": "Golf 8"}).json()
        assert renamed["name"] == "Golf 8"
        assert renamed["baseline_done"] is True
        assert renamed["alert_max_price"] is None

        capped = client.patch(f"/searches/{search_id}", json={"alert_max_price": 25000}).json()
        assert capped["alert_max_price"] == 25000.0
        assert capped["baseline_done"] is True
        kept = client.patch(f"/searches/{search_id}", json={"name": "Golf 8"}).json()
        assert kept["alert_max_price"] == 25000.0
        assert client.patch(f"/searches/{search_id}", json={"alert_max_price": 0}).status_code == 422
        cleared = client.patch(f"/searches/{search_id}", json={"alert_max_price": None}).json()
        assert cleared["alert_max_price"] is None
        quiet = client.patch(f"/searches/{search_id}", json={"unknown_policy": "quiet"}).json()
        assert (quiet["unknown_policy"], quiet["baseline_done"]) == ("quiet", True)
        assert client.patch(f"/searches/{search_id}", json={"unknown_policy": "maybe"}).status_code == 422

        same = client.patch(
            f"/searches/{search_id}", json={"filters": GOLF_FILTERS, "platforms": ["marktplaats"]}
        ).json()
        assert same["baseline_done"] is True

        changed = client.patch(
            f"/searches/{search_id}",
            json={"filters": {**GOLF_FILTERS, "year_min": 2020}, "active": False},
        ).json()
        assert changed["baseline_done"] is False
        assert changed["active"] is False
        assert "Bouwjaar: vanaf 2020" in changed["description"]

        seller = client.patch(f"/searches/{search_id}", json={"seller_type": "business"}).json()
        assert seller["seller_type"] == "business"
        assert "Verkoper: Bedrijf" in seller["description"]
        assert 10899 in json.loads(_source().query_json)["attribute_ids"]

        assert client.post(f"/searches/{search_id}/check-now").status_code == 200
        assert client.delete(f"/searches/{search_id}").status_code == 204
        assert client.get(f"/searches/{search_id}").status_code == 404
        assert _listings() == []
    finally:
        app.dependency_overrides.clear()


def test_api_rejects_unknown_model_and_platform() -> None:
    _reset_tables()
    client = _api_client(FakeFetcher())
    try:
        unknown_model = {**GOLF_FILTERS, "model": "Polo"}
        response = client.post(
            "/searches",
            json={"name": "x", "filters": unknown_model, "platforms": ["marktplaats"]},
        )
        assert response.status_code == 422
        assert "not available on Marktplaats" in response.json()["detail"]
        response = client.post(
            "/searches",
            json={"name": "x", "filters": GOLF_FILTERS, "platforms": ["ebay"]},
        )
        assert response.status_code == 422
        response = client.post(
            "/searches",
            json={"name": "x", "filters": {**GOLF_FILTERS, "year_min": 2022, "year_max": 2020},
                  "platforms": ["marktplaats"]},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def _insert_legacy_search() -> int:
    """A search as created before multi-platform support (pasted URL, no sources)."""
    with get_engine().begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO marketplace_searches (owner_id, marketplace, name, source_url, query_json, "
            "description_json, exclude_keywords_json, seller_type, alert_max_price, active, "
            "baseline_done, id_watermark, last_total_count, last_fetched_count, last_status, "
            "consecutive_failure_count, check_count, next_check_at, created_at, updated_at) "
            "VALUES ('local', 'marktplaats', 'Golf', 'https://www.marktplaats.nl/l/auto-s/x/', ?, "
            "'[\"Categorie: Auto''s\"]', '[]', 'all', 25000, 1, 1, 300, 2, 2, 'ok', 0, 4, "
            "'2026-11-24 10:00:00', '2026-11-20 10:00:00', '2026-11-20 10:00:00')",
            (json.dumps(GOLF_QUERY),),
        )
        return connection.exec_driver_sql("SELECT max(id) FROM marketplace_searches").scalar()


def test_legacy_search_gets_a_marktplaats_source_with_its_state() -> None:
    _reset_tables()
    search_id = _insert_legacy_search()
    init_db()
    init_db()  # idempotent

    with get_session_factory()() as session:
        sources = session.scalars(select(MarketplaceSearchSource)).all()
    assert len(sources) == 1
    source = sources[0]
    assert (source.search_id, source.marketplace) == (search_id, "marktplaats")
    assert json.loads(source.query_json) == GOLF_QUERY
    assert source.baseline_done is True
    assert source.id_watermark == 300
    assert source.last_complete is True
    assert source.check_count == 4

    # Checks keep working without a new baseline: m400 is new and alerts.
    _enable_alerts()
    fetcher = FakeFetcher()
    notifier = CollectingNotifier()
    _run(fetcher, notifier, search_payload([listing(400)]))
    assert [message.title for message in notifier.messages] == ["🆕 Nieuwe advertentie — Golf"]


def test_converting_a_legacy_search_to_equal_filters_keeps_its_baseline() -> None:
    _reset_tables()
    search_id = _insert_legacy_search()
    init_db()
    client = _api_client(FakeFetcher())
    try:
        assert client.patch(f"/searches/{search_id}", json={"seller_type": "private"}).status_code == 422
        converted = client.patch(
            f"/searches/{search_id}",
            json={"filters": GOLF_FILTERS, "platforms": ["marktplaats"]},
        ).json()
    finally:
        app.dependency_overrides.clear()
    assert converted["filters"]["model"] == "Golf"
    assert converted["baseline_done"] is True
    assert converted["description"][0] == "Auto: Volkswagen Golf"
    assert _source().id_watermark == 300
