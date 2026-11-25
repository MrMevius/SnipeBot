from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from marktplaats_fakes import CollectingNotifier, FakeAdapter, car
from snipebot.adapters.marketplaces.base import SearchFilters, SearchPage
from snipebot.core.config import get_settings
from snipebot.domain.marketplace_searches import (
    cheapest_listing,
    create_search,
    list_makes,
    list_models,
    preview_search,
    run_due_marketplace_searches,
    update_search,
)
from snipebot.domain.search_filters import check_listing, describe_filters, validate_filters
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import (
    AppSetting,
    MarketplaceListing,
    MarketplaceSearch,
    MarketplaceSearchSource,
)

FILTERS = SearchFilters(make="Tesla", model="Model 3", year_min=2024, battery_max=60)


def _reset() -> None:
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
    with get_session_factory()() as session:
        session.add_all(
            [
                AppSetting(key="notifications_enabled", value="true"),
                AppSetting(key="telegram_enabled", value="true"),
            ]
        )
        session.commit()


def _adapters() -> dict[str, FakeAdapter]:
    return {
        "marktplaats": FakeAdapter("marktplaats", "Marktplaats"),
        # The second platform cannot filter on battery capacity itself.
        "autotrack": FakeAdapter(
            "autotrack",
            "AutoTrack",
            models={"Tesla": ["Model 3", "Model Y"], "Polestar": ["2"]},
            post_filters=["battery"],
        ),
    }


def _create(adapters, platforms=("marktplaats", "autotrack")) -> int:
    with get_session_factory()() as session:
        return create_search(
            session,
            adapters,
            owner_id="local",
            name="Model 3 SR",
            filters=FILTERS,
            platforms=list(platforms),
            exclude_keywords=["schade"],
            seller_type="all",
            alert_max_price=Decimal("35000"),
        ).id


def _run(adapters, notifier) -> None:
    with get_session_factory()() as session:
        session.query(MarketplaceSearchSource).update(
            {MarketplaceSearchSource.next_check_at: datetime.now(UTC) - timedelta(seconds=1)}
        )
        session.commit()
        run_due_marketplace_searches(
            session, get_settings(), adapters=adapters, notifier=notifier
        )


def _rows() -> dict[str, MarketplaceListing]:
    with get_session_factory()() as session:
        return {row.item_id: row for row in session.scalars(select(MarketplaceListing))}


def test_makes_and_models_are_merged_by_name() -> None:
    adapters = _adapters()
    makes, warnings = list_makes(adapters)
    assert [(option.label, option.platforms) for option in makes] == [
        ("Polestar", ["autotrack"]),
        ("Tesla", ["marktplaats", "autotrack"]),
    ]
    assert warnings == []
    models, _ = list_models(adapters, "tesla")
    assert [(option.label, option.platforms) for option in models] == [
        ("Model 3", ["marktplaats", "autotrack"]),
        ("Model Y", ["autotrack"]),
    ]


def test_filters_validate_describe_and_check() -> None:
    filters = validate_filters(SearchFilters(make=" Tesla ", model="Model  3", range_min=600))
    assert (filters.make, filters.model) == ("Tesla", "Model 3")
    assert describe_filters(FILTERS, "private") == [
        "Auto: Tesla Model 3",
        "Bouwjaar: vanaf 2024",
        "Accucapaciteit: t/m 60 kWh",
        "Verkoper: Particulier",
    ]
    assert check_listing(FILTERS, car("x", "a", specs={"battery": 60}), ["battery"]) == (True, [])
    assert check_listing(FILTERS, car("x", "a", specs={"battery": 75}), ["battery"]) == (False, [])
    assert check_listing(FILTERS, car("x", "a"), ["battery"]) == (True, ["battery"])


def test_each_platform_is_checked_and_post_filtered() -> None:
    _reset()
    adapters = _adapters()
    notifier = CollectingNotifier()
    _create(adapters)

    # Baseline on both platforms; AutoTrack drops the 75 kWh car itself.
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m100")], complete=True))
    adapters["autotrack"].pages.append(
        SearchPage(
            3,
            [
                car("autotrack", "at-1", specs={"battery": 57}),
                car("autotrack", "at-2", specs={"battery": 75}),
                car("autotrack", "at-3"),
            ],
            complete=True,
        )
    )
    _run(adapters, notifier)
    assert notifier.messages == []
    assert adapters["autotrack"].queries[0] == {
        "make": "Tesla",
        "model": "Model 3",
        "seller": "all",
        "year": [2024, None],
    }
    assert adapters["marktplaats"].queries[0]["battery"] == [None, 60]
    rows = _rows()
    assert sorted(rows) == ["at-1", "at-3", "m100"]
    assert rows["at-3"].marketplace == "autotrack"
    assert rows["at-3"].unverified_filters_json == '["battery"]'

    # A new AutoTrack car without battery data alerts with a note and the platform.
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m100")], complete=True))
    adapters["autotrack"].pages.append(
        SearchPage(
            2,
            [car("autotrack", "at-4", price=31000), car("autotrack", "at-1", specs={"battery": 57})],
            complete=True,
        )
    )
    _run(adapters, notifier)
    assert [message.title for message in notifier.messages] == [
        "🆕 Nieuwe advertentie — Model 3 SR (AutoTrack)"
    ]
    assert "❔ Niet vermeld: accucapaciteit" in notifier.messages[0].body

    # Gone-marking is per platform: AutoTrack's at-3 left, Marktplaats is untouched.
    rows = _rows()
    assert rows["at-3"].gone_at is not None
    assert rows["m100"].gone_at is None
    with get_session_factory()() as session:
        search = session.scalars(select(MarketplaceSearch)).one()
        assert cheapest_listing(session, search).item_id == "m100"


def test_one_failing_platform_does_not_stop_the_other() -> None:
    _reset()
    adapters = _adapters()
    _create(adapters)
    from snipebot.adapters.marketplaces.base import MarketplaceError

    adapters["autotrack"].pages.append(MarketplaceError("blocked", "HTTP 403"))
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m1")], complete=True))
    _run(adapters, CollectingNotifier())

    with get_session_factory()() as session:
        sources = {s.marketplace: s for s in session.scalars(select(MarketplaceSearchSource))}
    assert sources["marktplaats"].last_status == "ok"
    assert sources["autotrack"].last_status == "blocked"
    assert sorted(_rows()) == ["m1"]


def test_preview_reports_each_platform() -> None:
    adapters = _adapters()
    adapters["autotrack"].pages.append(
        SearchPage(2, [car("autotrack", "at-1", specs={"battery": 75}), car("autotrack", "at-2")])
    )
    preview = preview_search(
        adapters,
        filters=SearchFilters(make="Tesla", model="Model Y", battery_max=60),
        platforms=["autotrack", "marktplaats"],
    )
    by_platform = {item.marketplace: item for item in preview.platforms}
    assert [item.marketplace for item in preview.platforms] == ["marktplaats", "autotrack"]
    assert by_platform["marktplaats"].error == "Model Y is not on Marktplaats"
    assert by_platform["autotrack"].total_count == 2
    assert by_platform["autotrack"].post_filters == ["battery"]
    assert [listing.item_id for listing in by_platform["autotrack"].sample] == ["at-2"]


def test_adding_and_removing_platforms() -> None:
    _reset()
    adapters = _adapters()
    search_id = _create(adapters, platforms=["marktplaats"])
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m1")], complete=True))
    _run(adapters, CollectingNotifier())

    with get_session_factory()() as session:
        search = session.get(MarketplaceSearch, search_id)
        update_search(session, adapters, search, platforms=["marktplaats", "autotrack"])
        sources = {source.marketplace: source for source in search.sources}
        # The existing platform keeps its baseline; the new one starts silently.
        assert sources["marktplaats"].baseline_done is True
        assert sources["autotrack"].baseline_done is False

        update_search(session, adapters, search, platforms=["autotrack"])
        assert [source.marketplace for source in search.sources] == ["autotrack"]
    assert _rows() == {}


def _alerts_for_unknown_battery(policy: str):
    _reset()
    adapters = _adapters()
    search_id = _create(adapters, platforms=["autotrack"])
    with get_session_factory()() as session:
        update_search(session, adapters, session.get(MarketplaceSearch, search_id), unknown_policy=policy)
    notifier = CollectingNotifier()
    adapters["autotrack"].pages.append(
        SearchPage(1, [car("autotrack", "at-1", specs={"battery": 57})], complete=True)
    )
    _run(adapters, notifier)
    adapters["autotrack"].pages.append(
        SearchPage(
            3,
            [
                car("autotrack", "at-2", price=31000),
                car("autotrack", "at-3", price=32000, specs={"battery": 58}),
                car("autotrack", "at-1", specs={"battery": 57}),
            ],
            complete=True,
        )
    )
    _run(adapters, notifier)
    return adapters, notifier, search_id


def test_unknown_values_can_be_kept_quietly() -> None:
    _, notifier, _ = _alerts_for_unknown_battery("quiet")
    assert ["Tesla Model 3 at-3" in message.body for message in notifier.messages] == [True]
    assert sorted(_rows()) == ["at-1", "at-2", "at-3"]


def test_unknown_values_can_be_left_out_and_back_in_silently() -> None:
    adapters, notifier, search_id = _alerts_for_unknown_battery("exclude")
    assert len(notifier.messages) == 1
    assert sorted(_rows()) == ["at-1", "at-3"]

    # Switching back records the left-out listings silently instead of alerting.
    with get_session_factory()() as session:
        search = session.get(MarketplaceSearch, search_id)
        update_search(session, adapters, search, unknown_policy="include")
        assert search.sources[0].baseline_done is False
    adapters["autotrack"].pages.append(
        SearchPage(2, [car("autotrack", "at-2", price=31000), car("autotrack", "at-1", specs={"battery": 57})], complete=True)
    )
    _run(adapters, notifier)
    assert len(notifier.messages) == 1
    assert _rows()["at-2"].from_baseline is True


def test_switching_to_exclude_removes_recorded_unknown_listings() -> None:
    adapters, _, search_id = _alerts_for_unknown_battery("include")
    assert "at-2" in _rows()
    with get_session_factory()() as session:
        update_search(session, adapters, session.get(MarketplaceSearch, search_id), unknown_policy="exclude")
    adapters["autotrack"].pages.append(
        SearchPage(1, [car("autotrack", "at-2", price=31000)], complete=True)
    )
    _run(adapters, CollectingNotifier())
    assert "at-2" not in _rows()


def test_distances_from_home() -> None:
    from marktplaats_fakes import FakeFetcher, listing, search_payload
    from scout24_fakes import FakeScout24, search_listing, search_page
    from snipebot.adapters.marketplaces.base import HomeLocation, distance_meters
    from snipebot.adapters.marketplaces.marktplaats import (
        TWEEDEHANDS,
        MarktplaatsAdapter,
        MarktplaatsClient,
    )
    from snipebot.adapters.marketplaces.scout24 import AUTOSCOUT24, Scout24Client

    daarle = HomeLocation(name="Daarle", latitude=52.4328, longitude=6.5374, postcode="7683")
    # Daarle → Gent is about 247 km in a straight line.
    assert 240_000 < distance_meters(daarle, 51.0543, 3.7174) < 255_000
    assert distance_meters(None, 51.0, 3.7) is None
    assert distance_meters(daarle, None, 3.7) is None

    fetcher = FakeFetcher()
    fetcher.payloads.append(
        search_payload([listing(1, distance_meters=-1000, coordinates=(51.0543, 3.7174))])
    )
    client = MarktplaatsClient(fetch=fetcher, site=TWEEDEHANDS, home=daarle)
    [car] = MarktplaatsAdapter(client).search({"l1_category_id": 91}).listings
    assert 240 < car.distance_meters / 1000 < 255

    fake = FakeScout24(AUTOSCOUT24)
    fake.search_pages.append({1: search_page([search_listing(1, site=AUTOSCOUT24, distance_km=182)])})
    page = Scout24Client(AUTOSCOUT24, fetch=fake, home=daarle).search({"cat": "ma1mo2"})
    assert "zip=7683&zipc=NL&zipr=2000" in fake.requests[-1]
    assert page.listings[0].distance_meters == 182_000


def test_variant_filter_is_checked_by_snipebot() -> None:
    _reset()
    adapters = _adapters()
    notifier = CollectingNotifier()
    with get_session_factory()() as session:
        search = create_search(
            session,
            adapters,
            owner_id="local",
            name="Model 3 SR",
            filters=SearchFilters(make="Tesla", model="Model 3", year_min=2024, variants=["sr"]),
            platforms=["autotrack"],
            exclude_keywords=[],
            seller_type="all",
            alert_max_price=Decimal("35000"),
            unknown_policy="exclude",
        )
        assert [source.post_filters_json for source in search.sources] == ['["variant"]']

    adapters["autotrack"].pages.append(
        SearchPage(
            3,
            [
                car("autotrack", "at-1", title="Tesla Model 3 Standard Range"),
                car("autotrack", "at-2", title="Tesla Model 3 Long Range AWD"),
                # Unknown from the search data; its page cannot be fetched here.
                car("autotrack", "at-3", title="Tesla Model 3"),
            ],
            complete=True,
        )
    )
    _run(adapters, notifier)
    rows = _rows()
    assert sorted(rows) == ["at-1"]
    assert '"variant": "sr"' in rows["at-1"].attributes_json

    adapters["autotrack"].pages.append(
        SearchPage(
            2,
            [car("autotrack", "at-4", title="Tesla Model 3 RWD", specs={"power": 208}), car("autotrack", "at-1", title="Tesla Model 3 Standard Range")],
            complete=True,
        )
    )
    _run(adapters, notifier)
    assert [message.title for message in notifier.messages] == [
        "🆕 Nieuwe advertentie — Model 3 SR"
    ]


def test_changed_filters_drop_listings_that_no_longer_match() -> None:
    _reset()
    adapters = _adapters()
    notifier = CollectingNotifier()
    search_id = _create(adapters, platforms=("autotrack",))
    page = lambda: SearchPage(  # noqa: E731
        2,
        [
            car("autotrack", "at-1", title="Tesla Model 3 Standard Range", specs={"battery": 60}),
            car("autotrack", "at-2", title="Tesla Model 3 Long Range AWD"),
        ],
        complete=True,
    )
    adapters["autotrack"].pages.append(page())
    _run(adapters, notifier)
    assert sorted(_rows()) == ["at-1", "at-2"]  # at-2: battery unknown, kept

    with get_session_factory()() as session:
        search = session.get(MarketplaceSearch, search_id)
        update_search(
            session,
            adapters,
            search,
            filters=SearchFilters(make="Tesla", model="Model 3", year_min=2024, variants=["sr"]),
        )
    adapters["autotrack"].pages.append(page())
    _run(adapters, notifier)
    assert sorted(_rows()) == ["at-1"]
    assert notifier.messages == []


def test_a_network_hiccup_is_retried_and_one_failed_check_stays_ok(monkeypatch) -> None:
    from snipebot.adapters.marketplaces.base import MarketplaceError
    from snipebot.domain import marketplace_searches

    monkeypatch.setattr(marketplace_searches, "FETCH_RETRY_DELAY_SECONDS", 0)
    _reset()
    adapters = _adapters()
    _create(adapters, platforms=("marktplaats",))
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m1")], complete=True))
    _run(adapters, CollectingNotifier())

    def source() -> MarketplaceSearchSource:
        with get_session_factory()() as session:
            return session.scalars(select(MarketplaceSearchSource)).one()

    def hiccup() -> MarketplaceError:
        return MarketplaceError("fetch_error", "Marktplaats request failed: [Errno -3] Temporary failure")

    # Fails once, the retry works.
    adapters["marktplaats"].pages.extend([hiccup(), SearchPage(1, [car("marktplaats", "m1")], complete=True)])
    _run(adapters, CollectingNotifier())
    assert (source().last_status, source().consecutive_failure_count) == ("ok", 0)

    # Retry fails too: still shown as ok, the next check comes sooner.
    adapters["marktplaats"].pages.extend([hiccup(), hiccup()])
    _run(adapters, CollectingNotifier())
    assert (source().last_status, source().consecutive_failure_count) == ("ok", 1)

    # The next check fails as well: now it is an error.
    adapters["marktplaats"].pages.extend([hiccup(), hiccup()])
    _run(adapters, CollectingNotifier())
    assert (source().last_status, source().consecutive_failure_count) == ("fetch_error", 2)
    assert "Temporary failure" in source().last_error_message

    # Other errors (blocked) show at once.
    adapters["marktplaats"].pages.append(SearchPage(1, [car("marktplaats", "m1")], complete=True))
    _run(adapters, CollectingNotifier())
    adapters["marktplaats"].pages.append(MarketplaceError("blocked", "HTTP 403"))
    _run(adapters, CollectingNotifier())
    assert source().last_status == "blocked"
