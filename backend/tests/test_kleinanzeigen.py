import html
import json
import subprocess

import pytest

from snipebot.adapters.marketplaces import kleinanzeigen
from snipebot.adapters.marketplaces.base import SearchFilters
from snipebot.adapters.marketplaces.kleinanzeigen import (
    KleinanzeigenAdapter,
    KleinanzeigenClient,
    KleinanzeigenError,
    island_props,
    parse_price,
    search_url,
)
from snipebot.adapters.marketplaces.kleinanzeigen_listing import parse_listing_page, validate_listing_url

BASE = "https://www.kleinanzeigen.de"
IMAGE = "https://img.kleinanzeigen.de/api/v1/prod-ads/images"


def astro(value):
    """Serialize like Astro island props: [0, value] plain, [1, [...]] array."""
    if isinstance(value, list):
        return [1, [astro(item) for item in value]]
    if isinstance(value, dict):
        return [0, {key: astro(item) for key, item in value.items()}]
    return [0, value]


def island(name: str, props: dict) -> str:
    serialized = {key: astro(value) for key, value in props.items()}
    return (
        f'<astro-island uid="x" component-url="/frontend-web/assets/{name}.Ab12.js" '
        f'props="{html.escape(json.dumps(serialized), quote=True)}"></astro-island>'
    )


def menu_item(key: str, label: str, url: str) -> dict:
    return {"key": key, "localizedName": label, "count": 3, "url": url, "menuItems": []}


def ad(number: int, **fields) -> dict:
    return {
        "organicAdPreview": {
            "id": 3500000000 + number,
            "topAd": False,
            "title": f"Tesla Model 3 Long Range {number}",
            "description": "Gepflegt",
            "seoLink": f"/s-anzeige/tesla-model-3-{number}/{3500000000 + number}-216-388",
            "price": "25.200 € VB",
            "posterType": "PRIVATE",
            "locationName": "66127",
            "parentLocationName": "Klarenthal",
            "attributes": ["70.810 km", "EZ 08/2020"],
            "imageList": [{"xLargeUrl": f"{IMAGE}/ff/{number:036d}?rule=$_59.AUTO"}],
            **fields,
        }
    }


def search_page(ads: list[dict], total: int, menus: list[dict] | None = None) -> str:
    return "".join(
        [
            "<html><body>",
            f'<span id="srp-breadcrumb-summary" class="x">1 - 25 von {total:,} Tesla Gebrauchtwagen</span>'.replace(",", "."),
            island("FilterChips", {"browseMenus": {"attributeMenus": [{"menuItems": menus or []}]}}),
            island("ImpressionTracker", {"resultAds": [{"sponsoredAdPresent": True}, *ads]}),
            "</body></html>",
        ]
    )


class FakeKleinanzeigen:
    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}
        self.requests: list[str] = []

    def __call__(self, url: str) -> str:
        self.requests.append(url)
        return self.pages.get(url, search_page([], 0))


def _adapter(fake: FakeKleinanzeigen, sleeps: list | None = None) -> KleinanzeigenAdapter:
    sleep = sleeps.append if sleeps is not None else (lambda _: None)
    return KleinanzeigenAdapter(KleinanzeigenClient(fetch=fake, sleep=sleep))


def test_island_props_revive_astro_serialization() -> None:
    page = island("ImpressionTracker", {"resultAds": [{"id": 1, "attributes": ["a", "b"]}]})
    assert island_props(page) == [("ImpressionTracker", {"resultAds": [{"id": 1, "attributes": ["a", "b"]}]})]


def test_taxonomy_and_query() -> None:
    makes = search_page(
        [],
        0,
        [
            menu_item("tesla", "Tesla", "/s-autos/tesla/c216+autos.marke_s:tesla"),
            menu_item("bmw", "BMW", "/s-autos/bmw/c216+autos.marke_s:bmw"),
            menu_item("privat", "Privat", "/s-autos/anbieter:privat/c216"),
        ],
    )
    models = search_page(
        [],
        0,
        [
            menu_item("model_3", "Model 3", "/s-autos/tesla/c216+autos.marke_s:tesla+autos.model_s:model_3"),
            menu_item("andere", "Weitere Tesla", "/s-autos/tesla/c216+autos.marke_s:tesla+autos.model_s:andere"),
        ],
    )
    fake = FakeKleinanzeigen(
        {f"{BASE}/s-autos/c216": makes, f"{BASE}/s-autos/tesla/c216+autos.marke_s:tesla": models}
    )
    adapter = _adapter(fake)
    assert [(make.id, make.label) for make in adapter.makes()] == [("tesla", "Tesla"), ("bmw", "BMW")]
    built = adapter.build_query(
        SearchFilters(make="Tesla", model="Model 3", year_min=2020, price_max=30000, mileage_max=150000, battery_min=70),
        "private",
    )
    assert built.query == {
        "make": "tesla",
        "model": "model_3",
        "year": "2020,",
        "price": ",30000",
        "mileage": ",150000",
        "poster": "privat",
    }
    assert built.post_filters == ["battery"]
    assert search_url(built.query, 2) == (
        f"{BASE}/s-autos/tesla/anbieter:privat/preis::30000/seite:2/sortierung:neuste/"
        "c216+autos.ez_i:2020%2C+autos.km_i:%2C150000+autos.marke_s:tesla+autos.model_s:model_3"
    )
    everyone = adapter.build_query(SearchFilters(make="Tesla", model="Model 3"), "all")
    assert everyone.query == {"make": "tesla", "model": "model_3"}
    with pytest.raises(KleinanzeigenError) as missing:
        adapter.build_query(SearchFilters(make="Tesla", model="Andere"), "all")
    assert missing.value.kind == "unsupported"
    with pytest.raises(KleinanzeigenError):
        search_url({"make": "../x", "model": "y"})


def test_search_reads_all_pages_without_top_ads() -> None:
    query = {"make": "tesla", "model": "model_3"}
    top = ad(99, topAd=True, title="Tesla Model Y")
    fake = FakeKleinanzeigen(
        {
            search_url(query): search_page([top, *[ad(n) for n in range(25)]], total=27),
            search_url(query, 2): search_page(
                [top, ad(24), ad(25, posterType="COMMERCIAL", price="1 € VB"), ad(26, title="Model 3 75 kWh", attributes=[])],
                total=27,
            ),
        }
    )
    sleeps: list[float] = []
    page = _adapter(fake, sleeps).search(query)
    assert fake.requests == [search_url(query), search_url(query, 2)]
    assert sleeps == [3.0]
    assert (page.total_count, len(page.listings), page.complete) == (27, 27, True)
    assert "k3500000099" not in {listing.item_id for listing in page.listings}

    car = page.listings[0]
    assert car.item_id == "k3500000000"
    assert car.marketplace == "kleinanzeigen"
    assert car.url == f"{BASE}/s-anzeige/tesla-model-3-0/3500000000-216-388"
    assert (car.price, car.price_type) == (25200, "NEGOTIABLE")
    assert car.city == "Klarenthal (DE)"
    assert car.seller_type == "private"
    assert car.specs == {"mileage": 70810, "year": 2020}
    assert car.attributes == {"country": "DE", "mileage": "70810", "constructionYear": "2020"}
    assert car.image_url.startswith(IMAGE)

    dealer, battery = page.listings[-2], page.listings[-1]
    assert (dealer.seller_type, dealer.price, dealer.price_type) == ("business", None, "NEGOTIABLE")
    assert battery.specs == {"battery": 75.0}


def test_search_without_result_data_is_a_parse_error() -> None:
    fake = FakeKleinanzeigen({search_url({"make": "tesla", "model": "model_3"}): "<html></html>"})
    with pytest.raises(KleinanzeigenError) as error:
        _adapter(fake).search({"make": "tesla", "model": "model_3"}, limit=5)
    assert error.value.kind == "parse_error"


def test_parse_price() -> None:
    assert parse_price("29.890 €") == (29890, "FIXED")
    assert parse_price("25.200 € VB") == (25200, "NEGOTIABLE")
    assert parse_price("VB") == (None, "NEGOTIABLE")
    assert parse_price("1 €") == (None, None)
    assert parse_price("Zu verschenken") == (None, None)


def _curl_result(status: int, body: bytes = b"<html></html>", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout=body + f"\n{status}".encode(), stderr=b"")


@pytest.mark.parametrize(
    ("status", "kind"), [(403, "blocked"), (429, "blocked"), (301, "gone"), (404, "gone"), (500, "fetch_error")]
)
def test_curl_status_handling(monkeypatch, status: int, kind: str) -> None:
    monkeypatch.setattr(kleinanzeigen.subprocess, "run", lambda *args, **kwargs: _curl_result(status))
    with pytest.raises(KleinanzeigenError) as error:
        kleinanzeigen.http_fetch(f"{BASE}/s-autos/c216")
    assert error.value.kind == kind


def test_curl_returns_body_and_sends_snipebot_user_agent(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command, **kwargs):
        calls.append(command)
        return _curl_result(200, b"<p>line one\nline two</p>")

    monkeypatch.setattr(kleinanzeigen.subprocess, "run", run)
    assert kleinanzeigen.http_fetch(f"{BASE}/s-autos/c216") == "<p>line one\nline two</p>"
    command = calls[0]
    assert command[0] == "curl"
    assert command[command.index("--user-agent") + 1].endswith("SnipeBot/0.1")
    assert "--location" not in command
    assert command[-2:] == ["--url", f"{BASE}/s-autos/c216"]


LISTING_URL = f"{BASE}/s-anzeige/tesla-model-3-long-range/3581555955-216-388"


def listing_page() -> str:
    gallery_image = (
        '<div class="galleryimage-element"><script type="application/ld+json">'
        '{{"contentUrl":"{url}","@type":"ImageObject"}}</script></div>'
    )
    return "".join(
        [
            "<html><head><script>window.BelenConf = {dimensions: "
            '{"ad_id":"3581555955","ad_seller_type":"Private"}};</script></head><body>',
            gallery_image.format(url=f"{IMAGE}/ff/ff438077-c338-44f1-a96f-72a30c384bb2?rule=$_59.AUTO"),
            gallery_image.format(url=f"{IMAGE}/a1/a1099eb4-4578-4f60-9c52-3f16fb262ab3?rule=$_59.AUTO"),
            '<div id="viewad-lightbox"></div>',
            '<h1 id="viewad-title" class="boxedarticle--title"> Tesla Model 3 Long Range</h1>',
            '<h2 class="boxedarticle--price" id="viewad-price"> 25.200 € VB</h2>',
            '<span id="viewad-locality" itemprop="addressLocality"> 66127 Saarbrücken-West - Klarenthal</span>',
            '<div class="splitlinebox l-container-row" id="viewad-details"><ul>',
            '<li class="addetailslist--detail"> Marke<span class="addetailslist--detail--value" itemprop="brand"> Tesla</span> </li>',
            '<li class="addetailslist--detail"> Modell<span class="addetailslist--detail--value" > Model 3</span> </li>',
            '<li class="addetailslist--detail"> Kilometerstand<span class="addetailslist--detail--value" > 70.810 km</span> </li>',
            "</ul></div>",
            '<div class="splitlinebox l-container-row" id="viewad-configuration"><ul class="checktaglist">',
            '<li class="checktag">Klimaanlage</li><li class="checktag">Sitzheizung</li></ul></div>',
            '<div class="splitlinebox"><p id="viewad-description-text" itemprop="description">',
            "Erste Hand<br />Scheckheft<script>x()</script></p></div>",
            '<div id="viewad-contact"><span class="text-body-regular-strong userprofile-vip">',
            '<a href="/s-bestandsliste.html?userId=1"> MA</a></span>',
            '<span class="userprofile-vip-details-text">Aktiv seit 07.08.2011</span></div>',
            # Other ads further down the page carry JSON-LD images too.
            '<script type="application/ld+json">{"contentUrl":"'
            f'{IMAGE}/00/00000000-0000-0000-0000-000000000000?rule=$_59.AUTO","@type":"ImageObject"}}</script>',
            "</body></html>",
        ]
    )


def test_listing_page_details() -> None:
    detail = parse_listing_page(listing_page(), url=LISTING_URL)
    assert detail.item_id == "k3581555955"
    assert detail.title == "Tesla Model 3 Long Range"
    assert (detail.price, detail.price_type) == (25200, "NEGOTIABLE")
    assert (detail.postcode, detail.city) == ("66127", "Klarenthal (DE)")
    assert detail.category == ["Tesla", "Model 3"]
    assert detail.description_text.startswith("Erste Hand")
    assert "script" not in detail.description_html
    assert [image.key for image in detail.images] == [
        "ff/ff438077-c338-44f1-a96f-72a30c384bb2",
        "a1/a1099eb4-4578-4f60-9c52-3f16fb262ab3",
    ]
    assert detail.attribute_groups == [
        {
            "label": "Fahrzeugdaten",
            "items": [
                {"key": "", "label": "Marke", "value": "Tesla"},
                {"key": "", "label": "Modell", "value": "Model 3"},
                {"key": "", "label": "Kilometerstand", "value": "70.810 km"},
            ],
        },
        {"label": "Ausstattung", "items": [{"key": "options", "label": "Ausstattung", "value": "Klimaanlage, Sitzheizung"}]},
    ]
    assert detail.seller == {
        "name": "MA",
        "sellerType": "CONSUMER",
        "activeSince": "07.08.2011",
        "city": "Klarenthal",
    }

    with pytest.raises(KleinanzeigenError) as missing:
        parse_listing_page("<html></html>", url=LISTING_URL)
    assert missing.value.kind == "parse_error"


def test_listing_url_validation() -> None:
    assert validate_listing_url(LISTING_URL + "?utm=x") == (LISTING_URL, "k3581555955")
    for url in (f"{BASE}/s-autos/c216", "https://evil.example/s-anzeige/x/1-216-1"):
        with pytest.raises(KleinanzeigenError) as error:
            validate_listing_url(url)
        assert error.value.kind == "invalid_url"


def test_registry_and_archive_offer_kleinanzeigen() -> None:
    from snipebot.adapters.marketplaces.platforms import PLATFORM_LABELS, get_adapters
    from snipebot.core.config import get_settings
    from snipebot.domain.marketplace_archive import ARCHIVE_MARKETPLACES, build_sources

    assert isinstance(get_adapters()["kleinanzeigen"], KleinanzeigenAdapter)
    assert PLATFORM_LABELS["kleinanzeigen"] == "Kleinanzeigen"
    assert "kleinanzeigen" in ARCHIVE_MARKETPLACES
    assert "kleinanzeigen" in build_sources(get_settings())
