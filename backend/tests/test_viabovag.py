import json

import pytest

from snipebot.adapters.marketplaces.base import HomeLocation, SearchFilters
from snipebot.adapters.marketplaces.viabovag import (
    ViaBovagAdapter,
    ViaBovagClient,
    ViaBovagError,
    parse_flight,
    search_url,
)
from snipebot.adapters.marketplaces.viabovag_listing import parse_listing_page

DAARLE = HomeLocation(name="Daarle", latitude=52.4328, longitude=6.5374, postcode="7683")
IMAGE = "https://stsharedprdweu.blob.core.windows.net/vehicles-media"


def flight_page(*records: str) -> str:
    """A page streaming ``records`` ("<id>:<payload>") like Next.js does, in two chunks."""
    payload = "".join(records)
    half = len(payload) // 2
    chunks = [payload[:half], payload[half:]]
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks
    )
    return f"<html><body>{scripts}</body></html>"


def text_record(key: str, text: str) -> str:
    return f"{key}:T{len(text.encode('utf-8')):x},{text}"


def result(number: int, **vehicle) -> dict:
    vehicle_id = f"00000000-0000-0000-0000-{number:012d}"
    return {
        "id": vehicle_id,
        "url": f"https://www.viabovag.nl/auto/aanbod/tesla-model-3-{number}",
        "imageUrl": f"{IMAGE}/{vehicle_id}/media.0001.jpg",
        "title": f"Tesla Model 3 {number}",
        "price": vehicle.pop("price", 35000),
        "vehicle": {
            "brand": "Tesla",
            "model": "Model 3",
            "mileage": 50000,
            "year": 2024,
            "fuelType": "Elektriciteit",
            "transmissionType": "Automatisch",
            "batteryCapacity": 60000,
            "specifiedBatteryRange": 513,
            "licensePlate": "GKK20H",
            **vehicle,
        },
        "company": {
            "name": "Dealer",
            "city": "DELFGAUW",
            "coordinates": {"latitude": 52.0, "longitude": 4.4, "isEmpty": False},
        },
    }


def search_page(results: list[dict], count: int | None = None) -> str:
    props = {
        "mobilityType": "car",
        "searchResults": {"results": results, "count": len(results) if count is None else count},
        "searchFacets": {
            "facets": [
                {
                    "name": "Brand",
                    "optionCategories": [
                        {"label": "Populair", "options": [{"name": "tesla", "label": "Tesla"}]},
                        {"label": "Alle", "options": [{"name": "tesla", "label": "Tesla"}, {"name": "bmw", "label": "BMW"}]},
                    ],
                },
                {"name": "Model", "options": [{"name": "model-3", "label": "Model 3"}]},
            ]
        },
    }
    return flight_page(
        '1:I[123,["a"],"default"]\n',
        text_record("2", "<p>Ëerste eigenaar</p>"),
        f'3:["$","$L4",null,{json.dumps(props)}]\n',
    )


class FakeViaBovag:
    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}
        self.requests: list[str] = []

    def __call__(self, url: str) -> str:
        self.requests.append(url)
        return self.pages.get(url, search_page([]))


def _adapter(fake: FakeViaBovag, sleeps: list | None = None) -> ViaBovagAdapter:
    sleep = sleeps.append if sleeps is not None else (lambda _: None)
    return ViaBovagAdapter(ViaBovagClient(fetch=fake, sleep=sleep, home=DAARLE))


def test_parse_flight_reads_json_and_text_records() -> None:
    records = parse_flight(search_page([result(1)]))
    assert records["2"] == "<p>Ëerste eigenaar</p>"
    assert records["3"][3]["searchResults"]["count"] == 1
    assert "1" not in records


def test_taxonomy_and_query() -> None:
    model_page = search_page([])
    fake = FakeViaBovag(
        {"https://www.viabovag.nl/auto": search_page([]), "https://www.viabovag.nl/auto/merk-tesla": model_page}
    )
    adapter = _adapter(fake)
    assert [(make.id, make.label) for make in adapter.makes()] == [("tesla", "Tesla"), ("bmw", "BMW")]
    built = adapter.build_query(
        SearchFilters(make="Tesla", model="Model 3", year_min=2024, battery_max=60), "business"
    )
    assert built.query == {"brand": "tesla", "model": "model-3"}
    assert built.post_filters == ["year", "battery"]
    with pytest.raises(ViaBovagError) as private:
        adapter.build_query(SearchFilters(make="Tesla", model="Model 3"), "private")
    assert private.value.kind == "unsupported"
    with pytest.raises(ViaBovagError):
        search_url({"brand": "../x", "model": "y"})


def test_search_reads_all_pages() -> None:
    first = "https://www.viabovag.nl/auto/merk-tesla/model-model-3"
    fake = FakeViaBovag(
        {
            first: search_page([result(n) for n in range(24)], count=26),
            f"{first}/pagina-2": search_page([result(23), result(24), result(25, batteryCapacity=None)], count=26),
        }
    )
    sleeps: list[float] = []
    page = _adapter(fake, sleeps).search({"brand": "tesla", "model": "model-3"})
    assert fake.requests == [first, f"{first}/pagina-2"]
    assert sleeps == [3.0]
    assert (page.total_count, len(page.listings), page.complete) == (26, 26, True)

    car = page.listings[0]
    assert car.marketplace == "viabovag"
    assert car.city == "Delfgauw"
    assert car.seller_type == "business"
    assert car.license_plate == "GKK20H"
    assert car.specs == {"year": 2024, "mileage": 50000, "range": 513, "battery": 60.0}
    assert car.attributes["country"] == "NL"
    assert 150 < car.distance_meters / 1000 < 170
    assert "battery" not in page.listings[-1].specs


def test_listing_page_details() -> None:
    advertisement = {
        "title": {"label": "Titel", "hasValue": True, "formattedValue": "Tesla Model 3 RWD"},
        "comments": {"label": "Toelichting", "hasValue": True, "formattedValue": "$2"},
        "price": {"label": "Prijs", "hasValue": True, "formattedValue": "€ 35.999,-"},
        "company": {
            "name": "iLectric Cars",
            "contact": {"phoneNumber": "0880000000"},
            "address": {"street": "De Steiger", "houseNumber": "128", "postalCode": "1351AL", "city": "ALMERE"},
        },
        "certainties": {
            "hasReturnWarranty": {"label": "BOVAG Omruilgarantie", "value": True},
            "hasNap": {"label": "NAP", "value": False},
        },
        "media": [
            {"type": "image", "url": f"{IMAGE}/abc/media.0001.jpg"},
            {"type": "video", "url": "https://example.test/video"},
            {"type": "image", "url": f"{IMAGE}/abc/media.0002.jpg"},
        ],
    }
    vehicle = {
        "general": {
            "brand": {"hasValue": True, "formattedValue": "Tesla"},
            "model": {"hasValue": True, "formattedValue": "Model 3"},
        },
        "identification": {"vehicleLicencePlate": {"hasValue": True, "formattedValue": "NDG-61-G"}},
        "specificationGroups": [
            {
                "name": "Algemeen",
                "specifications": [
                    {"label": "Merk", "hasValue": True, "formattedValue": "Tesla"},
                    {"label": "Leeg", "hasValue": False, "formattedValue": ""},
                ],
            }
        ],
        "accessories": [{"hasValue": True, "formattedValue": "ABS"}, {"hasValue": True, "formattedValue": "Navigatie"}],
    }
    page = flight_page(
        text_record("2", "<p>Dealer onderhouden<script>x()</script></p>"),
        "5:" + json.dumps(["$", "div", None, {"vehicle": {"id": "abc", "advertisement": advertisement, "vehicle": vehicle}}]) + "\n",
    )
    detail = parse_listing_page(page, url="https://www.viabovag.nl/auto/aanbod/x")
    assert detail.item_id == "abc"
    assert detail.price == 35999
    assert detail.description_html == "<p>Dealer onderhouden</p>"
    assert [image.key for image in detail.images] == ["abc/media.0001.jpg", "abc/media.0002.jpg"]
    assert detail.attribute_groups == [
        {"label": "Kenteken", "items": [{"key": "licensePlate", "label": "Kenteken", "value": "NDG61G"}]},
        {"label": "Algemeen", "items": [{"key": "", "label": "Merk", "value": "Tesla"}]},
        {"label": "Opties", "items": [{"key": "options", "label": "Opties", "value": "ABS, Navigatie"}]},
    ]
    assert detail.highlights == ["BOVAG Omruilgarantie"]
    assert detail.seller == {
        "sellerType": "TRADER",
        "name": "iLectric Cars",
        "address": "De Steiger 128, 1351AL, Almere",
        "city": "Almere",
        "phoneNumber": "0880000000",
    }
    assert detail.extra == {"license_plate": "NDG61G"}

    with pytest.raises(ViaBovagError) as missing:
        parse_listing_page(search_page([]), url="https://www.viabovag.nl/auto/aanbod/x")
    assert missing.value.kind == "parse_error"


def test_registry_offers_viabovag() -> None:
    from snipebot.adapters.marketplaces.platforms import PLATFORM_LABELS, get_adapters

    assert "viabovag" in get_adapters()
    assert PLATFORM_LABELS["viabovag"] == "ViaBOVAG"
