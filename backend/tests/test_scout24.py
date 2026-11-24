from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scout24_fakes import FakeScout24, listing_page, search_listing, search_page, uuid
from marktplaats_fakes import CollectingNotifier, FakeFetcher, FakeImages, listing_page_html
from snipebot.adapters.marketplaces import scout24_listing
from snipebot.adapters.marketplaces.scout24 import (
    AUTOSCOUT24,
    AUTOTRACK,
    Scout24Adapter,
    Scout24Client,
    Scout24Error,
    battery_kwh,
    original_image_url,
)
from snipebot.adapters.marketplaces.scout24_listing import parse_listing_page
from snipebot.adapters.marketplaces.base import MarketplaceError, SearchFilters
from snipebot.adapters.marketplaces.marktplaats import MarktplaatsAdapter
from snipebot.api.archive import get_archive_store
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_archive import (
    ArchiveSource,
    ArchiveStore,
    build_sources,
    reset_block_state,
    run_due_archive_fetches,
)
from snipebot.domain.marketplace_searches import create_search, run_due_marketplace_searches
from snipebot.main import app
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import (
    AppSetting,
    MarketplaceItem,
    MarketplaceListing,
    MarketplaceSearchSource,
)

FILTERS = SearchFilters(make="Tesla", model="Model 3", year_min=2024, range_min=550, battery_max=80)


def _adapter(fake: FakeScout24, sleeps: list[float] | None = None) -> Scout24Adapter:
    sleep = sleeps.append if sleeps is not None else (lambda _: None)
    return Scout24Adapter(fake.site, Scout24Client(fake.site, fetch=fake, sleep=sleep))


def test_taxonomy_and_query() -> None:
    adapter = _adapter(FakeScout24())
    assert [make.label for make in adapter.makes()] == ["Polestar", "Tesla"]
    built = adapter.build_query(
        SearchFilters(make="tesla", model="model 3", year_min=2024, price_max=40000, range_min=600),
        "all",
    )
    assert built.query == {"cat": "ma51520mo74665", "fregfrom": 2024, "priceto": 40000}
    assert built.post_filters == ["range"]

    with pytest.raises(Scout24Error) as private:
        adapter.build_query(FILTERS, "private")
    assert private.value.kind == "unsupported"
    with pytest.raises(Scout24Error, match="not available on AutoTrack"):
        adapter.build_query(SearchFilters(make="Tesla", model="Cybertruck"), "all")


def test_search_reads_all_pages_newest_first() -> None:
    fake = FakeScout24()
    fake.search_pages.append(
        {
            1: search_page([search_listing(1), search_listing(2)], total=3, pages=2),
            # Listings shift while paging: listing 2 shows up again.
            2: search_page([search_listing(2), search_listing(3, plate=None)], total=3, pages=2),
        }
    )
    sleeps: list[float] = []
    page = _adapter(fake, sleeps).search({"cat": "ma51520mo74665"})

    assert "sort=age&desc=1&page=1" in fake.requests[0]
    assert sleeps == [3.0]
    assert [listing.item_id for listing in page.listings] == [uuid(1), uuid(2), uuid(3)]
    assert page.total_count == 3
    assert page.complete is True

    listing = page.listings[0]
    assert listing.title == "Tesla Model 3 Long Range RWD 78 kWh"
    assert listing.price == Decimal(34950)
    assert listing.url.startswith("https://www.autotrack.nl/a/tesla-model-3-")
    assert listing.image_url.endswith(f"{uuid(1)}_photo0.jpg/720x540.jpg")
    assert listing.city == "Lelystad"
    assert listing.seller_type == "business"
    assert listing.license_plate == "S123AB"
    assert listing.specs == {"year": 2024, "mileage": 12345, "range": 600, "battery": 78.0}
    assert listing.attributes == {
        "constructionYear": "2024",
        "mileage": "12345",
        "fuel": "Elektrisch",
        "transmission": "Automatisch",
        "country": "NL",
    }
    assert page.listings[2].license_plate is None


def test_preview_reads_one_page() -> None:
    fake = FakeScout24()
    fake.search_pages.append({1: search_page([search_listing(1)], total=40, pages=2)})
    page = _adapter(fake).search({"cat": "ma51520mo74665"}, limit=20)
    assert page.complete is False
    assert len([url for url in fake.requests if "page=" in url]) == 1


def test_battery_and_images() -> None:
    assert battery_kwh("Long Range AWD 75 kWh | SOH 90%") == 75
    assert battery_kwh("Standard Range 57,5kWh") == 57.5
    assert battery_kwh("- (14,0 kWh/100 km)") is None
    assert original_image_url(
        "https://prod.pictures.autoscout24.net/listing-images/a_b.jpg/1280x960.webp"
    ) == "https://prod.pictures.autoscout24.net/listing-images/a_b.jpg"


def test_listing_page_details() -> None:
    detail = parse_listing_page(listing_page(5), url="https://www.autotrack.nl/a/x", site=AUTOTRACK)
    assert detail.item_id == uuid(5)
    assert detail.title == "Tesla Model 3 Long Range RWD 78 kWh"
    assert detail.price == Decimal(34950)
    assert detail.description_html == "Nette auto.<br><strong>Dealer onderhouden</strong>"
    assert [image.key for image in detail.images] == [f"{uuid(5)}_photo{n}" for n in range(3)]
    assert detail.images[0].url.endswith("_photo0.jpg")
    groups = {group["label"]: group["items"] for group in detail.attribute_groups}
    assert {"key": "licensePlate", "label": "Kenteken", "value": "S-123-AB"} in groups["Basis"]
    assert {"key": "electricRangeWithFallback", "label": "Actieradius", "value": "600 km"} in groups["Techniek"]
    assert {"key": "hadAccident", "label": "Ongeval gehad", "value": "Nee"} in groups["Historie"]
    assert groups["Opties"][0]["value"] == "Airconditioning, Stoelverwarming, ABS"
    assert detail.seller == {
        "name": "EV Dealer B.V.",
        "contactName": "Jan",
        "sellerType": "TRADER",
        "city": "Lelystad",
        "address": "Kempenaar 1, 8242 BA, Lelystad",
        "phoneNumber": "+31 (0)320 - 000000",
        "sellerProfileUrl": "https://www.autoscout24.nl/autobedrijven/ev-dealer",
        "rating": "4,8 (148 reviews)",
    }
    assert detail.stats == {"viewCount": 1397, "favoritedCount": 37, "since": "2026-11-05T11:26:29.042Z"}
    assert detail.extra == {"license_plate": "S123AB"}

    with pytest.raises(Scout24Error) as removed:
        parse_listing_page(search_page([]), url="https://www.autotrack.nl/a/x", site=AUTOTRACK)
    assert removed.value.kind == "gone"


# --- Searches and archive with AutoTrack --------------------------------------


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SNIPEBOT_MARKETPLACE_ARCHIVE_DIR", str(tmp_path / "archive"))
    get_settings.cache_clear()
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
    reset_block_state()
    yield get_settings()
    reset_block_state()
    get_settings.cache_clear()


def _sources(settings, fake: FakeScout24, fetcher: FakeFetcher, images: FakeImages):
    sources = build_sources(settings, fetch=fetcher, image_fetcher=images)
    sources[fake.site.key] = ArchiveSource(
        fetch_detail=lambda url: scout24_listing.fetch_listing(url, fake.site, fetch=fake),
        fetch_image=fake.image,
    )
    return sources


def _check(adapters) -> None:
    with get_session_factory()() as session:
        session.query(MarketplaceSearchSource).update(
            {MarketplaceSearchSource.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(
            session, get_settings(), adapters=adapters, notifier=CollectingNotifier()
        )


def test_autotrack_listings_are_searched_filtered_and_archived(settings) -> None:
    fake = FakeScout24()
    adapters = {"autotrack": _adapter(fake)}
    with get_session_factory()() as session:
        create_search(
            session,
            adapters,
            owner_id="local",
            name="Model 3",
            filters=FILTERS,
            platforms=["autotrack"],
            exclude_keywords=[],
            seller_type="all",
        )
    fake.search_pages.append(
        {
            1: search_page(
                [
                    search_listing(1),
                    search_listing(2, range_km=450),
                    search_listing(3, version="Performance", range_km=None, plate="X-999-ZZ"),
                ]
            )
        }
    )
    _check(adapters)

    with get_session_factory()() as session:
        rows = {row.item_id: row for row in session.scalars(select(MarketplaceListing))}
        assert sorted(rows) == [uuid(1), uuid(3)]
        assert rows[uuid(3)].unverified_filters_json == '["range", "battery"]'
        items = session.scalars(select(MarketplaceItem)).all()
        assert {(item.marketplace, item.item_id, item.license_plate) for item in items} == {
            ("autotrack", uuid(1), "S123AB"),
            ("autotrack", uuid(3), "X999ZZ"),
        }

    archived = run_due_archive_fetches(
        get_session_factory()(),
        settings,
        sources=_sources(settings, fake, FakeFetcher(), FakeImages()),
        sleep=lambda _: None,
    )
    assert archived == 2
    with get_session_factory()() as session:
        item = session.scalar(select(MarketplaceItem).where(MarketplaceItem.item_id == uuid(1)))
        assert item.status == "archived"
        assert item.seller_json.count("EV Dealer") == 1
        assert [image.file_path.split("/")[:2] for image in item.images] == [
            ["autotrack", uuid(1)]
        ] * 3
    assert all(url.endswith(".jpg") for url in fake.image_requests)


def test_blocked_platform_does_not_pause_the_other(settings) -> None:
    fake = FakeScout24()
    fake.listing_pages[uuid(1)] = Scout24Error("blocked", "HTTP 429")
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        for marketplace, item_id, url in (
            ("autotrack", uuid(1), f"https://www.autotrack.nl/a/x-{uuid(1)}"),
            ("autotrack", uuid(2), f"https://www.autotrack.nl/a/x-{uuid(2)}"),
            ("marktplaats", "m100", "https://www.marktplaats.nl/v/auto-s/tesla/m100-tesla"),
        ):
            session.add(
                MarketplaceItem(
                    owner_id="local",
                    marketplace=marketplace,
                    item_id=item_id,
                    url=url,
                    title="Tesla",
                    listing_title="Tesla",
                    status="pending",
                    first_seen_at=now,
                    last_seen_at=now,
                    next_fetch_at=now - timedelta(minutes=1),
                    fetch_failure_count=0,
                )
            )
        session.commit()

    sources = _sources(settings, fake, FakeFetcher(), FakeImages())
    with get_session_factory()() as session:
        run_due_archive_fetches(session, settings, sources=sources, sleep=lambda _: None)
    with get_session_factory()() as session:
        statuses = {item.item_id: item.status for item in session.scalars(select(MarketplaceItem))}
    assert statuses == {uuid(1): "pending", uuid(2): "pending", "m100": "archived"}
    # Only the first AutoTrack listing was tried; the rest waits for the backoff.
    assert len([url for url in fake.requests if "/a/" in url]) == 1


def test_duplicates_across_platforms_by_license_plate(settings, tmp_path) -> None:
    fake = FakeScout24()
    fetcher = FakeFetcher()
    now = datetime.now(UTC)
    with get_session_factory()() as session:
        session.add(AppSetting(key="notifications_enabled", value="false"))
        for marketplace, item_id, url in (
            ("autotrack", uuid(1), f"https://www.autotrack.nl/a/x-{uuid(1)}"),
            ("marktplaats", "m100", "https://www.marktplaats.nl/v/auto-s/tesla/m100-tesla"),
        ):
            session.add(
                MarketplaceItem(
                    owner_id="local",
                    marketplace=marketplace,
                    item_id=item_id,
                    url=url,
                    title="Tesla Model 3",
                    listing_title="Tesla Model 3",
                    status="pending",
                    first_seen_at=now,
                    last_seen_at=now,
                    next_fetch_at=now - timedelta(minutes=1),
                    fetch_failure_count=0,
                )
            )
        session.commit()

    # The Marktplaats car attributes carry the same plate in another notation.
    page = listing_page_html(100).replace(
        '{"key": "constructionYear", "label": "Bouwjaar", "value": 2021}',
        '{"key": "constructionYear", "label": "Bouwjaar", "value": 2021}, '
        '{"key": "licensePlate", "label": "Kenteken", "value": "s123ab"}',
    )
    fetcher.listing_pages["m100"] = page
    with get_session_factory()() as session:
        run_due_archive_fetches(
            session, settings, sources=_sources(settings, fake, fetcher, FakeImages()), sleep=lambda _: None
        )

    app.dependency_overrides[get_archive_store] = lambda: ArchiveStore(tmp_path / "archive")
    try:
        client = TestClient(app)
        items = client.get("/archive", params={"marketplace": "autotrack"}).json()["items"]
        assert [(item["marketplace"], item["item_id"]) for item in items] == [("autotrack", uuid(1))]
        detail = client.get(f"/archive/{items[0]['id']}").json()
        assert detail["license_plate"] == "S123AB"
        assert [(other["marketplace"], other["title"]) for other in detail["duplicates"]] == [
            ("marktplaats", "Volkswagen Golf 100")
        ]
    finally:
        app.dependency_overrides.clear()


def test_platform_registry_offers_scout24_sites() -> None:
    from snipebot.adapters.marketplaces.platforms import get_adapters

    assert list(get_adapters()) == ["marktplaats", "autoscout24", "autotrack"]
    assert isinstance(get_adapters()["marktplaats"], MarktplaatsAdapter)
    assert issubclass(Scout24Error, MarketplaceError)


# --- AutoScout24 ----------------------------------------------------------------


def test_autoscout24_searches_nl_be_de_with_private_sellers() -> None:
    fake = FakeScout24(AUTOSCOUT24)
    adapter = _adapter(fake)
    assert adapter.key == "autoscout24"
    built = adapter.build_query(SearchFilters(make="Tesla", model="Model 3", year_min=2024), "private")
    assert built.query == {"cat": "ma51520mo74665", "cy": "NL,B,D", "custtype": "P", "fregfrom": 2024}

    fake.search_pages.append(
        {
            1: search_page(
                [
                    search_listing(1, country="BE", seller="PrivateSeller", site=AUTOSCOUT24),
                    search_listing(2, site=AUTOSCOUT24),
                ]
            )
        }
    )
    page = adapter.search(built.query)
    assert "https://www.autoscout24.nl/lst?" in fake.requests[-1]
    assert "cy=NL%2CB%2CD" in fake.requests[-1]
    foreign, dutch = page.listings
    assert foreign.marketplace == "autoscout24"
    assert foreign.url.startswith("https://www.autoscout24.nl/aanbod/")
    assert (foreign.city, foreign.seller_type, foreign.attributes["country"]) == ("Lelystad (BE)", "private", "BE")
    assert dutch.city == "Lelystad"


def test_switching_autotrack_to_autoscout24_keeps_listings_and_archive(settings) -> None:
    autotrack = FakeScout24(AUTOTRACK)
    autoscout = FakeScout24(AUTOSCOUT24)
    adapters = {"autotrack": _adapter(autotrack), "autoscout24": _adapter(autoscout)}
    with get_session_factory()() as session:
        search_id = create_search(
            session,
            adapters,
            owner_id="local",
            name="Model 3",
            filters=SearchFilters(make="Tesla", model="Model 3"),
            platforms=["autotrack"],
            exclude_keywords=[],
            seller_type="all",
            alert_max_price=Decimal("50000"),
        ).id
    autotrack.search_pages.append({1: search_page([search_listing(1, price=36000)])})
    _check(adapters)
    sources = _sources(settings, autotrack, FakeFetcher(), FakeImages())
    with get_session_factory()() as session:
        run_due_archive_fetches(session, settings, sources=sources, sleep=lambda _: None)
    photos = len(autotrack.image_requests)
    assert photos == 3

    from snipebot.domain.marketplace_searches import update_search
    from snipebot.persistence.models import MarketplaceSearch

    with get_session_factory()() as session:
        update_search(session, adapters, session.get(MarketplaceSearch, search_id), platforms=["autoscout24"])

    notifier = CollectingNotifier()
    session_settings = get_settings()
    with get_session_factory()() as session:
        session.add_all(
            [AppSetting(key="notifications_enabled", value="true"), AppSetting(key="telegram_enabled", value="true")]
        )
        session.commit()
    autoscout.search_pages.append(
        {
            1: search_page(
                [
                    search_listing(1, price=35000, site=AUTOSCOUT24),
                    search_listing(2, country="DE", site=AUTOSCOUT24),
                ]
            )
        }
    )
    with get_session_factory()() as session:
        session.query(MarketplaceSearchSource).update(
            {MarketplaceSearchSource.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(session, session_settings, adapters=adapters, notifier=notifier)

    with get_session_factory()() as session:
        rows = {row.item_id: row for row in session.scalars(select(MarketplaceListing))}
        assert {key: row.marketplace for key, row in rows.items()} == {
            uuid(1): "autoscout24",
            uuid(2): "autoscout24",
        }
        assert [point.price for point in rows[uuid(1)].prices] == [Decimal(36000), Decimal(35000)]
        assert rows[uuid(1)].from_baseline is True
        items = {item.item_id: item for item in session.scalars(select(MarketplaceItem))}
        assert items[uuid(1)].marketplace == "autoscout24"
        assert items[uuid(1)].url.startswith("https://www.autoscout24.nl/")
        assert len(items[uuid(1)].images) == 3
    # The new baseline is silent; the known car's price drop does alert.
    assert [message.title for message in notifier.messages] == ["📉 Prijsdaling — Model 3"]

    with get_session_factory()() as session:
        session.query(MarketplaceItem).update(
            {MarketplaceItem.next_fetch_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_archive_fetches(
            session, settings, sources=_sources(settings, autoscout, FakeFetcher(), FakeImages()), sleep=lambda _: None
        )
    with get_session_factory()() as session:
        statuses = {item.item_id: item.status for item in session.scalars(select(MarketplaceItem))}
    assert statuses == {uuid(1): "archived", uuid(2): "archived"}
    assert any(f"/aanbod/tesla-model-3-cat_ma51520mo74665-{uuid(1)}" in url for url in autoscout.requests)
    # Known photos are not downloaded again after the move.
    assert all(uuid(1) not in url for url in autoscout.image_requests)
    assert len([url for url in autoscout.image_requests if uuid(2) in url]) == 3
