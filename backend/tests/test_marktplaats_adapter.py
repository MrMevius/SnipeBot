from decimal import Decimal

import pytest

from marktplaats_fakes import (
    CAR_FACETS,
    SEARCH_URL,
    FakeFetcher,
    listing,
    page_html,
    search_payload,
)
from snipebot.adapters.marketplaces.marktplaats import (
    AttributeRange,
    MarktplaatsClient,
    MarktplaatsError,
    SearchQuery,
    apply_fragment,
    apply_seller_type,
    describe_query,
    parse_listing,
    query_from_page_html,
    validate_search_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.example.com/l/auto-s/",
        "ftp://www.marktplaats.nl/l/auto-s/",
        "https://www.marktplaats.nl/v/auto-s/volkswagen/m123-golf",
        "https://www.marktplaats.nl/",
    ],
)
def test_validate_search_url_rejects_non_search_urls(url: str) -> None:
    with pytest.raises(MarktplaatsError) as exc_info:
        validate_search_url(url)
    assert exc_info.value.kind == "invalid_url"


def test_validate_search_url_splits_path_and_fragment() -> None:
    page_url, fragment = validate_search_url(
        "http://marktplaats.nl/l/auto-s/volkswagen/#f:10882|postcode:7671AB"
    )
    assert page_url == "https://www.marktplaats.nl/l/auto-s/volkswagen/"
    assert fragment == "f:10882|postcode:7671AB"


def test_query_from_page_html_reads_embedded_request() -> None:
    query, names = query_from_page_html(page_html())

    assert names == ["Auto's", "Volkswagen"]
    assert query.l1_category_id == 91
    assert query.l2_category_ids == [157]
    assert query.attribute_ids == [1260, 10882]
    assert query.query is None


def test_query_from_page_html_requires_search_data() -> None:
    with pytest.raises(MarktplaatsError) as exc_info:
        query_from_page_html("<html>no data</html>")
    assert exc_info.value.kind == "parse_error"


def test_apply_fragment_merges_browser_filters() -> None:
    query = SearchQuery(attribute_ids=[1260], ranges=[AttributeRange("constructionYear", low=2010)])

    warnings = apply_fragment(
        query,
        "f:10882,473|constructionYearFrom:2018|mileageTo:100000|PriceCentsTo:2500000"
        "|postcode:7671%20ab|distanceMeters:50000|q:golf+gti|offeredSince:Vandaag"
        "|ta:colour=Rood,Blauw|sortBy:SORT_INDEX|mystery:1",
    )

    assert query.attribute_ids == [1260, 10882, 473]
    assert [(item.key, item.low, item.high) for item in query.ranges] == [
        ("constructionYear", 2018, None),
        ("mileage", None, 100000),
        ("PriceCents", None, 2500000),
    ]
    assert query.postcode == "7671AB"
    assert query.distance_meters == 50000
    assert query.query == "golf gti"
    assert query.attributes_by_key == ["offeredSince:Vandaag", "colour:Rood", "colour:Blauw"]
    assert warnings == ["Ignored unknown filter mystery:1"]


def test_api_params_use_l2_category_list_and_null_bounds() -> None:
    query = SearchQuery(
        l1_category_id=91,
        l2_category_ids=[157],
        attribute_ids=[1260],
        ranges=[AttributeRange("mileage", high=100000)],
        postcode="7671AB",
        distance_meters=50000,
    )

    params = query.api_params(limit=100)

    assert ("l2CategoryIds[]", "157") in params
    assert ("attributeRanges[]", "mileage:null:100000") in params
    assert ("distanceMeters", "50000") in params
    assert ("sortBy", "SORT_INDEX") in params
    assert ("sortOrder", "DECREASING") in params
    assert ("limit", "100") in params


def test_query_round_trips_through_dict() -> None:
    query = SearchQuery(query="golf", ranges=[AttributeRange("PriceCents", 1, 2)])
    assert SearchQuery.from_dict(query.to_dict()) == query


def test_apply_seller_type_swaps_advertiser_filter() -> None:
    query = SearchQuery(attribute_ids=[1260, 10899])

    private = apply_seller_type(query, "private", CAR_FACETS)
    as_in_url = apply_seller_type(query, "all", CAR_FACETS)

    assert private.attribute_ids == [1260, 10898]
    assert as_in_url.attribute_ids == [1260, 10899]
    assert query.attribute_ids == [1260, 10899]


def test_apply_seller_type_requires_advertiser_facet() -> None:
    with pytest.raises(MarktplaatsError):
        apply_seller_type(SearchQuery(), "business", [])


def test_parse_listing_extracts_fields() -> None:
    parsed = parse_listing(listing(2469330984, price_cents=2175050, advertiser="Particulier"))

    assert parsed is not None
    assert parsed.item_id == "m2469330984"
    assert parsed.numeric_id == 2469330984
    assert parsed.price == Decimal("21750.50")
    assert parsed.url == "https://www.marktplaats.nl/v/auto-s/volkswagen/m2469330984-volkswagen-golf"
    assert parsed.image_url == "https://images.example.test/m2469330984_85.jpg"
    assert parsed.seller_type == "private"
    assert parsed.attributes["mileage"] == "64500"
    assert parsed.distance_meters == 12000


def test_parse_listing_handles_unknown_distance_and_price() -> None:
    raw = listing(1, price_cents=0, distance_meters=-1000)
    raw["priceInfo"]["priceType"] = "SEE_DESCRIPTION"
    parsed = parse_listing(raw)

    assert parsed is not None
    assert parsed.price is None
    assert parsed.distance_meters is None
    assert parse_listing({"itemId": "m1"}) is None


def test_describe_query_uses_facet_labels() -> None:
    query = SearchQuery(
        l1_category_id=91,
        l2_category_ids=[157],
        attribute_ids=[1260, 10882, 10898],
        ranges=[
            AttributeRange("constructionYear", low=2018),
            AttributeRange("mileage", high=100000),
            AttributeRange("PriceCents", low=500000, high=2500000),
        ],
        postcode="7671AB",
        distance_meters=50000,
    )

    lines = describe_query(query, CAR_FACETS, ["Auto's", "Volkswagen"])

    assert lines == [
        "Categorie: Auto's › Volkswagen",
        "Model: Golf",
        "Type advertentie: Te koop",
        "Adverteerder: Particulier",
        "Bouwjaar: vanaf 2018",
        "Kilometerstand: t/m 100.000 km",
        "Prijs: € 5.000 t/m € 25.000",
        "Afstand: binnen 50 km van 7671AB",
    ]


def test_client_resolves_url_and_searches() -> None:
    fetcher = FakeFetcher()
    fetcher.payloads.append(search_payload([listing(2), listing(1)], total=86))
    client = MarktplaatsClient(fetch=fetcher)

    resolved = client.resolve(SEARCH_URL)
    page = client.search(resolved.query)

    assert fetcher.requests[0] == "https://www.marktplaats.nl/l/auto-s/volkswagen/f/golf/1260/"
    assert "postcode=7671AB" in fetcher.requests[1]
    assert "attributeRanges%5B%5D=PriceCents%3Anull%3A2500000" in fetcher.requests[1]
    assert resolved.warnings == []
    assert page.total_count == 86
    assert [item.item_id for item in page.listings] == ["m2", "m1"]


def test_client_rejects_invalid_json() -> None:
    client = MarktplaatsClient(fetch=lambda url, accept: "not json")
    with pytest.raises(MarktplaatsError) as exc_info:
        client.search(SearchQuery())
    assert exc_info.value.kind == "parse_error"
