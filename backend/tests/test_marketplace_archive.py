import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from marktplaats_fakes import (
    CollectingNotifier,
    FakeFetcher,
    FakeImages,
    listing,
    listing_page_html,
    search_payload,
)
from snipebot.adapters.marketplaces.marktplaats import MarktplaatsClient, MarktplaatsError
from snipebot.adapters.marketplaces.marktplaats_listing import (
    image_fetch,
    parse_listing_page,
    validate_listing_url,
)
from snipebot.api.archive import get_archive_store
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_archive import (
    ArchiveStore,
    reset_block_state,
    run_due_archive_fetches,
)
from snipebot.domain.marketplace_searches import create_search, run_due_marketplace_searches
from snipebot.main import app
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import (
    MarketplaceItem,
    MarketplaceItemImage,
    MarketplaceListing,
    MarketplaceSearch,
)

LISTING_URL = "https://www.marktplaats.nl/v/auto-s/volkswagen/m5-volkswagen-golf"


@pytest.fixture(autouse=True)
def _clean_tables():
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
            "marketplace_searches",
        ):
            connection.exec_driver_sql(f"DELETE FROM {table}")
    reset_block_state()
    yield
    reset_block_state()


@pytest.fixture
def settings(tmp_path):
    return get_settings().model_copy(
        update={
            "marketplace_archive_dir": str(tmp_path / "archive"),
            "marketplace_archive_delay_seconds": 0,
            "marketplace_archive_tick_budget_seconds": 3600,
        }
    )


# --- Listing page parser -------------------------------------------------------


def test_parse_car_listing_page() -> None:
    detail = parse_listing_page(listing_page_html(5), url=LISTING_URL)

    assert detail.item_id == "m5"
    assert detail.price == Decimal("15000")
    assert detail.category == ["Auto's", "Volkswagen"]
    assert detail.attribute_groups == [
        {
            "label": "Basis",
            "items": [
                {"key": "constructionYear", "label": "Bouwjaar", "value": "2021"},
                {"key": "mileage", "label": "Kilometerstand", "value": "64.500 km"},
            ],
        },
        {
            "label": "Opties",
            "items": [{"key": "options", "label": "Opties", "value": "ABS, Cruise Control"}],
        },
    ]
    assert [image.key for image in detail.images] == ["media-a", "media-b"]
    assert detail.images[0].url == (
        "https://images.marktplaats.com/api/v1/listing/images/a?rule=ecg_mp_eps$_85.jpg"
    )
    assert detail.seller["name"] == "Testverkoper"
    assert detail.seller["sellerProfileUrl"] == "https://www.marktplaats.nl/u/testverkoper/1/"
    assert "phoneNumber" not in detail.seller  # hidden by the seller
    assert detail.stats == {"viewCount": 12, "favoritedCount": 1, "since": "2026-11-20T10:00:00Z"}
    assert detail.highlights == ["Eerste eigenaar"]
    assert detail.city == "Almelo"
    assert detail.description_html == "<strong>Nette auto</strong><br>Eerste eigenaar."
    assert detail.description_text == "Nette auto\nEerste eigenaar."


def test_parse_listing_page_sanitizes_description() -> None:
    description = (
        '<p onclick="x()">Hallo <a href="https://evil.test">link</a> &amp; meer</p>'
        '<script>alert(1)</script><img src=x onerror="alert(2)"><ul><li>Een<li>Twee</ul>'
        "<div><em>open"
    )
    detail = parse_listing_page(listing_page_html(5, description=description), url=LISTING_URL)

    assert detail.description_html == (
        "<p>Hallo link &amp; meer</p><ul><li>Een<li>Twee</li></li></ul><em>open</em>"
    )
    assert "alert" not in detail.description_text


def test_parse_generic_listing_reads_rendered_attributes() -> None:
    detail = parse_listing_page(listing_page_html(5, car=False), url=LISTING_URL)

    assert detail.attribute_groups == [
        {
            "label": "Kenmerken",
            "items": [
                {"key": "", "label": "Conditie", "value": "Gebruikt"},
                {"key": "", "label": "Merk", "value": "Gazelle"},
            ],
        }
    ]


def test_parse_listing_page_requires_embedded_data() -> None:
    with pytest.raises(MarktplaatsError) as exc_info:
        parse_listing_page("<html></html>", url=LISTING_URL)
    assert exc_info.value.kind == "parse_error"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.example.com/v/auto-s/m1-golf",
        "https://www.marktplaats.nl/l/auto-s/",
        "ftp://www.marktplaats.nl/v/auto-s/m1-golf",
    ],
)
def test_validate_listing_url_rejects_other_urls(url: str) -> None:
    with pytest.raises(MarktplaatsError):
        validate_listing_url(url)


def test_image_fetch_only_allows_marktplaats_images() -> None:
    with pytest.raises(MarktplaatsError):
        image_fetch("https://evil.test/image.jpg")


def test_content_hash_ignores_statistics() -> None:
    first = parse_listing_page(listing_page_html(5), url=LISTING_URL)
    second = parse_listing_page(listing_page_html(5), url=LISTING_URL)
    second.stats["viewCount"] = 99
    assert first.content_hash() == second.content_hash()


# --- Archive worker ---------------------------------------------------------------


def _create_search(fetcher: FakeFetcher) -> int:
    with get_session_factory()() as session:
        return create_search(
            session,
            MarktplaatsClient(fetch=fetcher),
            owner_id="local",
            name="Golf",
            url="https://www.marktplaats.nl/l/auto-s/volkswagen/",
            exclude_keywords=[],
            seller_type="all",
        ).id


def _check_search(fetcher: FakeFetcher, settings, payload) -> None:
    fetcher.payloads.append(payload)
    with get_session_factory()() as session:
        session.query(MarketplaceSearch).update(
            {MarketplaceSearch.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(
            session,
            settings,
            client=MarktplaatsClient(fetch=fetcher),
            notifier=CollectingNotifier(),
        )


def _archive(fetcher: FakeFetcher, images: FakeImages, settings, **kwargs) -> int:
    with get_session_factory()() as session:
        return run_due_archive_fetches(
            session, settings, fetch=fetcher, image_fetcher=images, **kwargs
        )


def _make_due() -> None:
    with get_session_factory()() as session:
        session.query(MarketplaceItem).update(
            {MarketplaceItem.next_fetch_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()


def _item(item_id: str) -> MarketplaceItem:
    session = get_session_factory()()
    return session.scalar(select(MarketplaceItem).where(MarketplaceItem.item_id == item_id))


def test_search_listings_are_archived_with_photos(settings, tmp_path) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5), listing(4)]))

    pending = _item("m5")
    assert pending.status == "pending"  # baseline listings are archived too
    assert pending.price == Decimal("15000")

    assert _archive(fetcher, images, settings) == 2

    item = _item("m5")
    assert item.status == "archived"
    assert item.title == "Volkswagen Golf 5"
    assert json.loads(item.seller_json)["name"] == "Testverkoper"
    assert len(item.versions) == 1
    assert [image.source_key for image in item.images] == ["media-a", "media-b"]
    stored = tmp_path / "archive" / item.images[0].file_path
    assert stored.read_bytes().startswith(b"jpeg:https://images.marktplaats.com/")
    assert item.next_fetch_at.replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(days=6)
    assert len(images.requests) == 4

    # Not due again: nothing is fetched.
    assert _archive(fetcher, images, settings) == 0


def test_refetch_stores_version_only_on_change(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5)]))
    _archive(fetcher, images, settings)

    _make_due()
    _archive(fetcher, images, settings)
    assert len(_item("m5").versions) == 1
    assert len(images.requests) == 2  # known photos are not downloaded again

    fetcher.listing_pages["m5"] = listing_page_html(
        5, description="<strong>Nette auto</strong><br />Nieuwe APK.", images=("b", "c")
    )
    _make_due()
    _archive(fetcher, images, settings)

    item = _item("m5")
    assert len(item.versions) == 2
    removed = {image.source_key: image.removed_at for image in item.images}
    assert removed["media-a"] is not None
    assert removed["media-b"] is None and removed["media-c"] is None

    client = TestClient(app)
    detail = client.get(f"/archive/{item.id}").json()
    latest = detail["versions"][0]
    assert latest["description_diff"] == ["-Eerste eigenaar.", "+Nieuwe APK."]
    assert latest["images_added"] == 1
    assert latest["images_removed"] == 1
    assert detail["versions"][1]["fields"] == []
    # Current photos first, the removed one last.
    assert [image["removed_at"] is None for image in detail["images"]] == [True, True, False]


def test_price_change_in_search_triggers_refetch(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5)]))
    _archive(fetcher, images, settings)

    _check_search(fetcher, settings, search_payload([listing(5, price_cents=1400000)]))
    item = _item("m5")
    assert item.next_fetch_at.replace(tzinfo=UTC) <= datetime.now(UTC)
    assert [point.price for point in item.prices] == [Decimal("15000"), Decimal("14000")]

    fetcher.listing_pages["m5"] = listing_page_html(5, price_cents=1400000)
    _archive(fetcher, images, settings)
    item = _item("m5")
    assert len(item.prices) == 2
    assert len(item.versions) == 2


def test_removed_listing_is_marked_gone_and_revived(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5), listing(4)]))
    _archive(fetcher, images, settings)

    # The search no longer shows m5; the archive checks the listing page.
    fetcher.listing_pages["m5"] = MarktplaatsError("gone", "removed")
    _check_search(fetcher, settings, search_payload([listing(4)]))
    _archive(fetcher, images, settings)

    item = _item("m5")
    assert item.status == "gone"
    assert item.gone_at is not None
    assert item.next_fetch_at is None
    assert len(item.images) == 2  # the archive is kept

    _check_search(fetcher, settings, search_payload([listing(5), listing(4)]))
    item = _item("m5")
    assert item.gone_at is None
    assert item.status == "archived"


def test_blocked_requests_pause_the_archive(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5), listing(4)]))

    images.error = MarktplaatsError("blocked", "HTTP 429")
    assert _archive(fetcher, images, settings) == 1
    assert _item("m5").status == "pending"

    images.error = None
    assert _archive(fetcher, images, settings) == 0  # paused

    reset_block_state()
    assert _archive(fetcher, images, settings) == 2


def test_fetch_failures_back_off(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5)]))
    fetcher.listing_pages["m5"] = MarktplaatsError("fetch_error", "HTTP 500")

    _archive(fetcher, images, settings)

    item = _item("m5")
    assert item.status == "pending"
    assert item.fetch_failure_count == 1
    assert item.last_error_message == "HTTP 500"
    assert item.next_fetch_at.replace(tzinfo=UTC) > datetime.now(UTC)


def test_worker_throttles_between_listings(settings) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5), listing(4), listing(3)]))
    sleeps: list[float] = []
    ticks = iter([0, 1, 100, 100])

    processed = _archive(
        fetcher,
        images,
        settings.model_copy(
            update={
                "marketplace_archive_delay_seconds": 3,
                "marketplace_archive_tick_budget_seconds": 50,
            }
        ),
        sleep=sleeps.append,
        clock=lambda: next(ticks),
    )

    assert processed == 2
    assert sleeps.count(3) == 1


def test_existing_listings_are_backfilled(settings) -> None:
    fetcher = FakeFetcher()
    _create_search(fetcher)
    with get_session_factory()() as session:
        search = session.scalar(select(MarketplaceSearch))
        session.add(
            MarketplaceListing(
                search_id=search.id,
                item_id="m7",
                title="Volkswagen Golf 7",
                url="https://www.marktplaats.nl/v/auto-s/volkswagen/m7-volkswagen-golf",
                current_price=Decimal("9000"),
                first_price=Decimal("9000"),
                attributes_json="{}",
                from_baseline=True,
                first_seen_at=datetime(2026, 11, 20, tzinfo=UTC),
                last_seen_at=datetime(2026, 11, 20, tzinfo=UTC),
            )
        )
        session.commit()

    _archive(fetcher, FakeImages(), settings)

    item = _item("m7")
    assert item.status == "archived"
    assert item.first_seen_at.replace(tzinfo=UTC) == datetime(2026, 11, 20, tzinfo=UTC)


def test_archive_disabled_does_nothing(settings) -> None:
    fetcher = FakeFetcher()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5)]))
    disabled = settings.model_copy(update={"marketplace_archive_enabled": False})
    assert _archive(fetcher, FakeImages(), disabled) == 0


# --- API -------------------------------------------------------------------------------


def test_archive_api(settings, tmp_path) -> None:
    fetcher = FakeFetcher()
    images = FakeImages()
    search_id = _create_search(fetcher)
    fetcher.listing_pages["m4"] = listing_page_html(4, description="Golf GTI met schuifdak")
    _check_search(fetcher, settings, search_payload([listing(5), listing(4)]))
    _archive(fetcher, images, settings)
    app.dependency_overrides[get_archive_store] = lambda: ArchiveStore(tmp_path / "archive")
    client = TestClient(app)
    try:
        listings = client.get(f"/searches/{search_id}/listings").json()["items"]
        archive_ids = {row["item_id"]: row["archive_id"] for row in listings}
        assert all(archive_ids.values())

        page = client.get("/archive", params={"sort": "title", "order": "asc"}).json()
        assert page["total"] == 2
        assert [item["item_id"] for item in page["items"]] == ["m4", "m5"]
        assert page["items"][0]["searches"] == [{"id": search_id, "name": "Golf"}]
        assert page["usage"]["images"] == 4
        assert page["usage"]["bytes"] > 0

        found = client.get("/archive", params={"q": "schuifdak"}).json()
        assert [item["item_id"] for item in found["items"]] == ["m4"]
        assert client.get("/archive", params={"status": "gone"}).json()["total"] == 0
        assert client.get("/archive", params={"search_id": search_id}).json()["total"] == 2

        detail = client.get(f"/archive/{archive_ids['m5']}").json()
        assert detail["description_html"] == "<strong>Nette auto</strong><br>Eerste eigenaar."
        assert detail["attribute_groups"][0]["label"] == "Basis"
        assert detail["price_history"] == [
            {"price": 15000.0, "observed_at": detail["price_history"][0]["observed_at"]}
        ]

        image = client.get(f"/archive/images/{detail['cover_image_id']}")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert image.content.startswith(b"jpeg:")

        refreshed = client.post(f"/archive/{archive_ids['m5']}/refresh").json()
        assert refreshed["next_fetch_at"] is not None

        # Deleting the search keeps the archive.
        assert client.delete(f"/searches/{search_id}").status_code == 204
        assert client.get("/archive").json()["total"] == 2

        folder = tmp_path / "archive" / "marktplaats" / "m5"
        assert folder.is_dir()
        assert client.delete(f"/archive/{archive_ids['m5']}").status_code == 204
        assert not folder.exists()
        assert client.get(f"/archive/{archive_ids['m5']}").status_code == 404
        with get_session_factory()() as session:
            assert session.scalar(select(MarketplaceItemImage).where(
                MarketplaceItemImage.item_id == archive_ids["m5"]
            )) is None
    finally:
        app.dependency_overrides.pop(get_archive_store, None)


def test_archive_detail_is_owner_scoped(settings) -> None:
    fetcher = FakeFetcher()
    _create_search(fetcher)
    _check_search(fetcher, settings, search_payload([listing(5)]))
    item = _item("m5")

    client = TestClient(app)
    assert client.get(f"/archive/{item.id}", headers={"x-owner-id": "someone-else"}).status_code == 404
    assert client.get("/archive", headers={"x-owner-id": "someone-else"}).json()["total"] == 0
