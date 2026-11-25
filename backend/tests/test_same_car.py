import json
from dataclasses import dataclass, replace
from decimal import Decimal

from fastapi.testclient import TestClient

from marktplaats_fakes import CollectingNotifier, car
from snipebot.adapters.marketplaces.base import SearchPage
from snipebot.domain.same_car import group_same_cars, same_car
from snipebot.main import app
from test_multi_platform_searches import _adapters, _create, _reset, _run


@dataclass
class Row:
    marketplace: str
    title: str
    city: str | None
    current_price: Decimal | None
    attributes_json: str


def row(marketplace: str, price: int | None, *, mileage="104350", year="2024", city="Veghel", title=None) -> Row:
    return Row(
        marketplace=marketplace,
        title=title or "Tesla Model 3 Premium Long Range AWD 78 kWh - 94% SoH, Winterpak",
        city=city,
        current_price=Decimal(price) if price is not None else None,
        attributes_json=json.dumps({"mileage": mileage, "constructionYear": year}),
    )


def test_same_car_needs_year_mileage_place_or_title_and_close_price() -> None:
    mp = row("marktplaats", 33400)
    assert same_car(mp, row("autoscout24", 33400, title="Tesla Model 3 LR AWD"))
    assert same_car(mp, row("autoscout24", 35000, city="Elders"))  # same title start
    assert same_car(row("kleinanzeigen", 42999, city="Hamburg Barmbek (DE)"), row("autoscout24", 45000, city="Hamburg", title="x"))
    assert same_car(mp, row("viabovag", None))
    assert not same_car(mp, row("marktplaats", 33400))  # one platform holds a car once
    assert not same_car(mp, row("autoscout24", 33400, mileage="104351"))
    assert not same_car(mp, row("autoscout24", 33400, year="2025"))
    assert not same_car(mp, row("autoscout24", 33400, city="Bruxelles", title="Tesla Model 3 RWD"))
    assert not same_car(mp, row("autoscout24", 38000))  # too far apart in price
    assert not same_car(row("marktplaats", 45000, mileage="10"), row("autoscout24", 45000, mileage="10"))


def test_two_cars_of_one_dealer_with_the_same_mileage_stay_apart() -> None:
    def aalsmeer(marketplace: str, price: int) -> Row:
        return row(marketplace, price, mileage="30000", city="Aalsmeer", title="Tesla Model 3 Long Range RWD + HW4")

    rows = [
        aalsmeer("marktplaats", 44240),
        aalsmeer("marktplaats", 42890),
        aalsmeer("autoscout24", 42890),
        aalsmeer("autoscout24", 44240),
        aalsmeer("viabovag", 44240),
        row("autoscout24", 33400),
    ]
    groups = group_same_cars(rows)
    assert [[(r.marketplace, int(r.current_price)) for r in group] for group in groups] == [
        [("marktplaats", 44240), ("autoscout24", 44240), ("viabovag", 44240)],
        [("marktplaats", 42890), ("autoscout24", 42890)],
        [("autoscout24", 33400)],
    ]


def _veghel(marketplace: str, item_id: str, price: int):
    listing = car(marketplace, item_id, price=price, title="Tesla Model 3 Long Range AWD - 94% SoH")
    return replace(listing, attributes={"mileage": "104350", "constructionYear": "2024"})


def test_same_car_on_another_platform_is_one_result_without_a_second_alert() -> None:
    _reset()
    adapters = _adapters()
    notifier = CollectingNotifier()
    search_id = _create(adapters)
    for adapter in adapters.values():
        adapter.pages.append(SearchPage(0, [], complete=True))
    _run(adapters, notifier)

    # The car appears on Marktplaats first: one alert.
    adapters["marktplaats"].pages.append(SearchPage(1, [_veghel("marktplaats", "m1", 33400)], complete=True))
    adapters["autotrack"].pages.append(SearchPage(0, [], complete=True))
    _run(adapters, notifier)
    assert len(notifier.messages) == 1

    # The same car on AutoTrack for the same price: no second alert.
    adapters["marktplaats"].pages.append(SearchPage(1, [_veghel("marktplaats", "m1", 33400)], complete=True))
    adapters["autotrack"].pages.append(
        SearchPage(1, [replace(_veghel("autotrack", "at-1", 33400), specs={"battery": 57})], complete=True)
    )
    _run(adapters, notifier)
    assert len(notifier.messages) == 1

    # Cheaper on AutoTrack: that is news.
    adapters["marktplaats"].pages.append(SearchPage(1, [_veghel("marktplaats", "m1", 33400)], complete=True))
    adapters["autotrack"].pages.append(
        SearchPage(1, [replace(_veghel("autotrack", "at-1", 32900), specs={"battery": 57})], complete=True)
    )
    _run(adapters, notifier)
    assert len(notifier.messages) == 2
    assert notifier.messages[1].title.startswith("📉")

    client = TestClient(app)
    items = client.get(f"/searches/{search_id}/listings").json()["items"]
    assert len(items) == 1
    assert (items[0]["item_id"], items[0]["current_price"]) == ("at-1", 32900)
    assert [(other["marketplace"], other["current_price"]) for other in items[0]["also_listed"]] == [
        ("marktplaats", 33400)
    ]
    summary = client.get(f"/searches/{search_id}").json()
    assert summary["listing_count"] == 1
