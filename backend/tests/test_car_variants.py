import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from snipebot.adapters.marketplaces.base import Listing, MarketplaceError, SearchFilters, power_kw
from snipebot.adapters.marketplaces.marktplaats_listing import ListingDetail
from snipebot.core.config import get_settings
from snipebot.domain.car_variants import classify, detail_variants, supports_variants
from snipebot.domain.search_filters import check_listing, describe_filters, validate_filters
from snipebot.domain.variant_resolution import resolve_variants
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import MarketplaceItem, MarketplaceVariantCache


def variants(*keys: str) -> frozenset[str]:
    return frozenset(keys)


@pytest.mark.parametrize(
    ("title", "kwargs", "expected"),
    [
        ("Tesla Model 3 Long Range AWD", {}, variants("lr_awd")),
        ("Tesla Model 3 Premium Long Range RWD 78 kWh", {}, variants("lr_rwd")),
        ("Tesla Highland Max Reichweite/Hinterantrieb10/25", {}, variants("lr_rwd")),
        ("Tesla Model 3 Long Range", {}, variants("lr_rwd", "lr_awd")),
        ("Tesla Model 3 Long Range", {"power_kw": 366}, variants("lr_awd")),
        ("Tesla Model 3 Performance", {"power_kw": 375}, variants("performance")),
        ("Tesla Model 3 Standard Range Plus", {}, variants("sr")),
        ("Tesla standart model", {}, variants("sr")),
        # "Premium" says nothing; battery and power decide.
        ("Tesla Model 3 Premium LFP RWD", {"battery_kwh": 60, "power_kw": 208}, variants("sr")),
        ("Tesla Model 3 RWD", {}, variants("sr", "lr_rwd")),
        ("Tesla Model 3 RWD", {"range_km": 702}, variants("lr_rwd")),
        ("Tesla Model 3 Dual Motor", {}, variants("lr_awd", "performance")),
        # A field filled in wrongly is ignored when it contradicts the title.
        ("Tesla Model 3 78 kWh RWD Long Range", {"power_kw": 208}, variants("lr_rwd")),
        ("Tesla Model 3 2026 – 208 kW – Full Option", {"drive": "4x4 permanent"}, variants("sr")),
        ("Tesla Model 3 Standardausstattung", {}, None),
        ("Tesla Model 3", {}, None),
    ],
)
def test_classify(title, kwargs, expected) -> None:
    assert classify(title, **kwargs) == expected


def test_detail_variants_read_labelled_attributes() -> None:
    groups = [
        {
            "label": "Specificaties",
            "items": [
                {"label": "Uitvoering", "value": "Premium LFP RWD + HW4"},
                {"label": "Accu-capaciteit", "value": "60 kWh"},
                {"label": "Accu conditie", "value": "98 kWh"},
                {"label": "Vermogen", "value": "283 pk"},
                {"label": "Aandrijving", "value": "Achterwiel"},
            ],
        }
    ]
    assert detail_variants("Tesla Model 3", groups) == variants("sr")
    assert detail_variants("Tesla Model 3", [{"items": [{"label": "Leistung", "value": "498 PS"}]}]) == variants("lr_awd")


def test_power_kw() -> None:
    assert power_kw("208 kW (283 PK)") == 208
    assert power_kw("498pk (366kW)") == 366
    assert power_kw("320 pk") == 235
    assert power_kw("Elektrisch") is None


def test_filter_validation_and_check() -> None:
    assert supports_variants("Tesla", "Model 3")
    assert not supports_variants("Tesla", "Model Y")
    filters = validate_filters(
        SearchFilters(make="Tesla", model="Model 3", year_min=2024, variants=["lr_awd", "lr_rwd"])
    )
    assert filters.variants == ["lr_rwd", "lr_awd"]
    assert filters.active_keys() == ["year", "variant"]
    assert "Uitvoering: Long Range RWD, Long Range AWD" in describe_filters(filters)
    for wrong in (
        SearchFilters(make="Tesla", model="Model Y", year_min=2024, variants=["sr"]),
        SearchFilters(make="Tesla", model="Model 3", year_min=2021, variants=["sr"]),
        SearchFilters(make="Tesla", model="Model 3", year_min=2024, variants=["plaid"]),
    ):
        with pytest.raises(ValueError):
            validate_filters(wrong)

    def listing(variant: str | None) -> Listing:
        return _listing("x", attributes={"variant": variant} if variant else {})

    assert check_listing(filters, listing("lr_awd"), ["variant"]) == (True, [])
    assert check_listing(filters, listing("lr_awd,lr_rwd"), ["variant"]) == (True, [])
    assert check_listing(filters, listing("sr"), ["variant"]) == (False, [])
    assert check_listing(filters, listing("lr_awd,performance"), ["variant"]) == (True, ["variant"])
    assert check_listing(filters, listing(None), ["variant"]) == (True, ["variant"])


def _listing(item_id: str, title: str = "Tesla Model 3", **fields) -> Listing:
    values = {
        "item_id": item_id,
        "title": title,
        "description": "",
        "url": f"https://www.kleinanzeigen.de/s-anzeige/x/{item_id[1:] or 1}-216-1",
        "image_url": None,
        "price": Decimal(30000),
        "price_type": None,
        "city": None,
        "distance_meters": None,
        "attributes": {},
        "seller_type": None,
        "marketplace": "kleinanzeigen",
        **fields,
    }
    return Listing(**values)


def _detail(title: str, power: str) -> ListingDetail:
    return ListingDetail(
        item_id="k1",
        title=title,
        url="https://example.test",
        price=None,
        price_type=None,
        category=[],
        description_html="",
        description_text="",
        attribute_groups=[{"label": "Fahrzeugdaten", "items": [{"key": "", "label": "Leistung", "value": power}]}],
        images=[],
        seller={},
        stats={},
        highlights=[],
        city=None,
        postcode=None,
        is_reserved=False,
    )


@pytest.fixture()
def db_session():
    get_settings.cache_clear()
    init_db()
    with get_engine().begin() as connection:
        for table in ("marketplace_variant_cache", "marketplace_item_versions", "marketplace_item_images", "marketplace_item_prices", "marketplace_items"):
            connection.exec_driver_sql(f"DELETE FROM {table}")
    session = get_session_factory()()
    yield session
    session.close()


def test_resolve_variants_uses_search_data_archive_cache_and_pages(db_session) -> None:
    now = datetime.now(UTC)
    db_session.add(
        MarketplaceItem(
            owner_id="local",
            marketplace="kleinanzeigen",
            item_id="k2",
            url="https://example.test/2",
            title="Tesla Model 3",
            listing_title="Tesla Model 3",
            attribute_groups_json=json.dumps([{"items": [{"label": "Leistung", "value": "627 PS"}]}]),
            first_seen_at=now,
            last_seen_at=now,
            archived_at=now,
        )
    )
    db_session.commit()
    pages: list[str] = []

    def fetch(url: str) -> ListingDetail:
        pages.append(url)
        if url.endswith("/4-216-1"):
            raise MarketplaceError("gone", "removed")
        return _detail("Tesla Model 3", "283 PS")

    listings = [
        _listing("k1", "Tesla Model 3 Long Range AWD"),  # search data
        _listing("k2"),  # archive: Performance
        _listing("k3"),  # page: SR
        _listing("k4"),  # page gone: stays unknown
    ]
    sleeps: list[float] = []
    resolve_variants(db_session, "kleinanzeigen", listings, fetch_detail=fetch, sleep=sleeps.append, now=now)
    db_session.commit()
    assert [listing.attributes.get("variant") for listing in listings] == ["lr_awd", "performance", "sr", None]
    assert len(pages) == 2 and sleeps == [2.0]

    # Cached: no pages fetched again, also not for the listing whose page told nothing.
    again = [_listing("k2"), _listing("k3")]
    resolve_variants(db_session, "kleinanzeigen", again, fetch_detail=fetch, now=now + timedelta(minutes=10))
    assert [listing.attributes.get("variant") for listing in again] == ["performance", "sr"]
    assert len(pages) == 2
    cached = {row.item_id: row.variants for row in db_session.query(MarketplaceVariantCache)}
    assert cached == {"k2": "performance", "k3": "sr"}

    # A changed title resolves again; the page budget is respected.
    renamed = [_listing("k3", "Tesla Model 3 neu"), _listing("k5"), _listing("k6")]
    resolve_variants(db_session, "kleinanzeigen", renamed, fetch_detail=fetch, max_fetches=1, now=now)
    assert len(pages) == 3
    assert [listing.attributes.get("variant") for listing in renamed] == ["sr", None, None]
