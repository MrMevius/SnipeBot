from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from marktplaats_fakes import (
    CollectingNotifier,
    FakeFetcher,
    listing,
    search_payload,
)
from snipebot.adapters.marketplaces.base import SearchFilters
from snipebot.adapters.marketplaces.marktplaats import (
    TWEEDEHANDS,
    MarktplaatsAdapter,
    MarktplaatsClient,
)
from snipebot.adapters.marketplaces.marktplaats_listing import fetch_listing
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_searches import create_search, run_due_marketplace_searches
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import (
    AppSetting,
    MarketplaceItem,
    MarketplaceListing,
    MarketplaceSearchSource,
)

FILTERS = SearchFilters(make="Volkswagen", model="Golf", year_min=2018)


def _adapter(fetcher: FakeFetcher, site=None) -> MarktplaatsAdapter:
    site = site or TWEEDEHANDS
    return MarktplaatsAdapter(MarktplaatsClient(fetch=fetcher, site=site))


def test_2dehands_uses_the_marktplaats_api_on_its_own_site() -> None:
    fetcher = FakeFetcher()
    adapter = _adapter(fetcher)
    assert (adapter.key, adapter.label) == ("2dehands", "2dehands")
    built = adapter.build_query(FILTERS, "private")
    assert built.post_filters == []
    assert built.query["attribute_ids"] == [1260, 10882, 10898]

    # Range and battery are checked by SnipeBot: Belgian sellers rarely state them.
    ev = adapter.build_query(
        SearchFilters(make="Volkswagen", model="Golf", year_min=2024, range_min=400, battery_max=60), "all"
    )
    assert ev.post_filters == ["range", "battery"]
    assert [item["key"] for item in ev.query["ranges"]] == ["constructionYear"]

    fetcher.payloads.append(search_payload([listing(100, title="Volkswagen ID.3 Pro 58 kWh")]))
    page = adapter.search(built.query)
    assert fetcher.requests[-1].startswith("https://www.2dehands.be/lrp/api/search?")
    [car] = page.listings
    assert car.marketplace == "2dehands"
    assert car.url == "https://www.2dehands.be/v/auto-s/volkswagen/m100-volkswagen-golf"
    assert car.city == "Almelo (BE)"
    assert car.specs["battery"] == 58


def test_2dehands_listing_page() -> None:
    fetcher = FakeFetcher()
    detail = fetch_listing(
        "https://www.2ememain.be/v/auto-s/volkswagen/m100-volkswagen-golf", fetch=fetcher, site=TWEEDEHANDS
    )
    assert fetcher.requests == ["https://www.2dehands.be/v/auto-s/volkswagen/m100-volkswagen-golf"]
    assert detail.seller["sellerProfileUrl"] == "https://www.2dehands.be/u/testverkoper/1/"
    assert detail.city == "Almelo (BE)"
    assert detail.title == "Volkswagen Golf 100"


def test_listing_on_marktplaats_and_2dehands_is_recorded_once() -> None:
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
    marktplaats, tweedehands = FakeFetcher(), FakeFetcher()
    adapters = {
        "marktplaats": MarktplaatsAdapter(MarktplaatsClient(fetch=marktplaats)),
        "2dehands": _adapter(tweedehands),
    }
    with get_session_factory()() as session:
        session.add_all(
            [AppSetting(key="notifications_enabled", value="true"), AppSetting(key="telegram_enabled", value="true")]
        )
        session.commit()
        create_search(
            session,
            adapters,
            owner_id="local",
            name="Golf",
            filters=FILTERS,
            platforms=["marktplaats", "2dehands"],
            exclude_keywords=[],
            seller_type="all",
            alert_max_price=Decimal("100000"),
        )

    notifier = CollectingNotifier()

    def run(mp, td):
        marktplaats.payloads.append(search_payload(mp))
        tweedehands.payloads.append(search_payload(td))
        with get_session_factory()() as session:
            session.query(MarketplaceSearchSource).update(
                {MarketplaceSearchSource.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
            )
            session.commit()
            run_due_marketplace_searches(session, get_settings(), adapters=adapters, notifier=notifier)

    run([listing(100)], [listing(200)])
    # The seller also shows m300 in Belgium; it is recorded and alerted once.
    run([listing(300), listing(100)], [listing(300), listing(200)])
    run([listing(300), listing(100)], [listing(300), listing(200)])

    with get_session_factory()() as session:
        rows = {row.item_id: row.marketplace for row in session.scalars(select(MarketplaceListing))}
        items = {(item.marketplace, item.item_id) for item in session.scalars(select(MarketplaceItem))}
    assert rows == {"m100": "marktplaats", "m200": "2dehands", "m300": "marktplaats"}
    assert ("2dehands", "m300") not in items
    assert len(notifier.messages) == 1
    assert "Volkswagen Golf 300" in notifier.messages[0].body
