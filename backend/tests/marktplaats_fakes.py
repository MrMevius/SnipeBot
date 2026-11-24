"""Synthetic Marktplaats payloads shaped like the real search API responses."""

from __future__ import annotations

import json
from typing import Any

ADVERTISER_FACET = {
    "id": 2166,
    "key": "advertiser",
    "type": "AttributeGroupFacet",
    "label": "Adverteerder",
    "attributeGroup": [
        {"attributeValueKey": "Particulier", "attributeValueId": 10898, "attributeValueLabel": "Particulier"},
        {"attributeValueKey": "Bedrijf", "attributeValueId": 10899, "attributeValueLabel": "Bedrijf"},
    ],
}
MODEL_FACET = {
    "id": 159,
    "key": "model",
    "type": "AttributeGroupFacet",
    "label": "Model",
    "attributeGroup": [
        {"attributeValueKey": "Golf", "attributeValueId": 1260, "attributeValueLabel": "Golf"},
    ],
}
PRICE_TYPE_FACET = {
    "id": 2162,
    "key": "priceType",
    "type": "AttributeGroupFacet",
    "label": "Type advertentie",
    "attributeGroup": [
        {"attributeValueKey": "Vraagprijs", "attributeValueId": 10882, "attributeValueLabel": "Te koop"},
    ],
}
YEAR_FACET = {"id": 1597, "key": "constructionYear", "type": "AttributeRangeFacet", "label": "Bouwjaar"}
MILEAGE_FACET = {"id": 1598, "key": "mileage", "type": "AttributeRangeFacet", "label": "Kilometerstand"}
CAR_FACETS = [ADVERTISER_FACET, PRICE_TYPE_FACET, YEAR_FACET, MILEAGE_FACET, MODEL_FACET]
CATEGORY_FACET = {
    "id": 0,
    "key": "RelevantCategories",
    "type": "CategoryTreeFacet",
    "categories": [
        {"id": 91, "label": "Auto's", "key": "auto-s", "parentId": None},
        {"id": 157, "label": "Volkswagen", "key": "volkswagen", "parentId": 91},
        {"id": 2830, "label": "Tesla", "key": "tesla", "parentId": 91},
    ],
}
# Query of the Golf search built from GOLF_FILTERS (and of the legacy SEARCH_URL).
GOLF_QUERY = {
    "query": None,
    "l1_category_id": 91,
    "l2_category_ids": [157],
    "attribute_ids": [1260, 10882],
    "attributes_by_key": [],
    "ranges": [
        {"key": "constructionYear", "low": 2018, "high": None},
        {"key": "PriceCents", "low": None, "high": 2500000},
        {"key": "mileage", "low": None, "high": 100000},
    ],
    "postcode": None,
    "distance_meters": None,
}

SEARCH_URL = (
    "https://www.marktplaats.nl/l/auto-s/volkswagen/f/golf/1260/"
    "#f:10882|constructionYearFrom:2018|mileageTo:100000|PriceCentsTo:2500000"
    "|postcode:7671AB|distanceMeters:50000|sortBy:SORT_INDEX|sortOrder:DECREASING"
)


def listing(
    number: int,
    *,
    title: str | None = None,
    price_cents: int = 1500000,
    description: str = "Nette auto",
    advertiser: str | None = None,
    distance_meters: int = 12000,
    coordinates: tuple[float, float] | None = None,
    country_name: str = "Nederland",
) -> dict[str, Any]:
    item_id = f"m{number}"
    extended = [{"key": "advertiser", "value": advertiser, "values": [advertiser]}] if advertiser else []
    return {
        "itemId": item_id,
        "title": title or f"Volkswagen Golf {number}",
        "description": description,
        "priceInfo": {"priceCents": price_cents, "priceType": "FIXED"},
        "location": {
            "cityName": "Almelo",
            "countryName": country_name,
            "distanceMeters": distance_meters,
            **(
                {"latitude": coordinates[0], "longitude": coordinates[1]}
                if coordinates
                else {}
            ),
        },
        "date": "Vandaag",
        "imageUrls": [f"//images.example.test/{item_id}_82.jpg"],
        "pictures": [
            {
                "mediumUrl": f"https://images.example.test/{item_id}_82.jpg",
                "extraExtraLargeUrl": f"https://images.example.test/{item_id}_85.jpg",
            }
        ],
        "priorityProduct": "DAGTOPPER",
        "attributes": [
            {"key": "constructionYear", "value": "2021", "values": ["2021"]},
            {"key": "mileage", "value": "64500", "values": ["64500"]},
            {"key": "fuel", "value": "Benzine", "values": ["Benzine"]},
            {"key": "transmission", "value": "Automaat", "values": ["Automaat"]},
        ],
        "extendedAttributes": extended,
        "vipUrl": f"/v/auto-s/volkswagen/{item_id}-volkswagen-golf",
    }


def search_payload(
    listings: list[dict[str, Any]], *, total: int | None = None, facets=None
) -> dict[str, Any]:
    return {
        "listings": listings,
        "topBlock": [],
        "facets": CAR_FACETS if facets is None else facets,
        "totalResultCount": len(listings) if total is None else total,
    }


def page_html(original_request: dict[str, Any] | None = None) -> str:
    request = original_request or {
        "categories": {
            "l1Category": {"id": 91, "key": "auto-s", "fullName": "Auto's"},
            "l2Categories": [{"id": 157, "key": "volkswagen", "fullName": "Volkswagen"}],
        },
        "attributesById": [1260, 10882],
        "attributesByKey": [],
        "attributeRanges": [],
        "distance": {"postcode": ""},
    }
    data = {
        "props": {
            "pageProps": {
                "searchRequestAndResponse": {
                    "listings": [],
                    "searchRequest": {"originalRequest": request},
                }
            }
        }
    }
    return (
        "<html><body><div id=\"__next\"></div>"
        f"<script id=\"__NEXT_DATA__\" type=\"application/json\" crossorigin=\"anonymous\">{json.dumps(data)}</script>"
        "</body></html>"
    )


def listing_page_html(
    number: int,
    *,
    title: str | None = None,
    price_cents: int = 1500000,
    description: str = "<strong>Nette auto</strong><br />Eerste eigenaar.",
    images: tuple[str, ...] = ("a", "b"),
    car: bool = True,
    seller_name: str = "Testverkoper",
) -> str:
    """A listing page with ``window.__CONFIG__`` data and rendered markup."""
    item_id = f"m{number}"
    listing_data: dict[str, Any] = {
        "itemId": item_id,
        "title": title or f"Volkswagen Golf {number}",
        "priceInfo": {"priceCents": price_cents, "priceType": "FIXED"},
        "category": {"id": 157, "name": "Volkswagen", "parentName": "Auto's"},
        "gallery": {
            "imageUrls": [],
            "media": {
                "imageSizes": {"XXL": "85"},
                "images": [
                    {
                        "mediaId": f"media-{key}",
                        "base": f"//images.marktplaats.com/api/v1/listing/images/{key}?rule=ecg_mp_eps$_#.jpg",
                    }
                    for key in images
                ],
            },
        },
        "seller": {
            "id": 1,
            "name": seller_name,
            "sellerType": "CONSUMER",
            "sellerProfileUrl": "/u/testverkoper/1/",
            "activeSinceDiff": "2 jaar",
            "phoneNumber": "0600000000",
            "phoneNumberHidden": True,
            "location": {"cityName": "Almelo", "postcode": "7600AA"},
        },
        "stats": {"viewCount": 12, "favoritedCount": 1, "since": "2026-11-20T10:00:00Z"},
        "highlights": [{"key": "Eerste eigenaar"}],
        "isReserved": False,
    }
    if car:
        listing_data["carAttributes"] = {
            "groupedWithIcons": [
                {"key": "Main", "attributes": [{"key": "mileage", "label": "Kilometerstand", "value": "64.500", "unit": "km"}]},
                {
                    "key": "Basics",
                    "attributes": [
                        {"key": "constructionYear", "label": "Bouwjaar", "value": 2021},
                        {"key": "mileage", "label": "Kilometerstand", "value": "64.500", "unit": "km"},
                    ],
                },
                {"key": "Options", "attributes": [{"key": "options", "label": "Opties", "values": ["ABS", "Cruise Control"]}]},
            ]
        }
    attributes_html = (
        ""
        if car
        else '<div class="Attributes-module-root"><div class="Attributes-module-list">'
        '<div class="Attributes-module-item"><div class="Attributes-module-label">Conditie</div>'
        '<div class="Attributes-module-value">Gebruikt</div></div>'
        '<div class="Attributes-module-item"><div class="Attributes-module-label">Merk</div>'
        '<div class="Attributes-module-value"><a href="/l/x/">Gazelle</a></div></div></div></div>'
    )
    return (
        "<html><head><script>window.__ENV_CONFIG__ = {};</script></head><body>"
        f'<div class="Description-module-description"><div data-collapsable="description">{description}</div></div>'
        f"{attributes_html}"
        f"<script>window.__CONFIG__ = {json.dumps({'listing': listing_data})};</script>"
        "</body></html>"
    )


class FakeFetcher:
    """Serves result pages, queued API payloads and listing pages.

    ``listing_pages`` maps item ids to page HTML or to an exception to raise.
    """

    def __init__(self, html: str | None = None) -> None:
        self.html = html or page_html()
        self.payloads: list[dict[str, Any]] = []
        self.default_payload: dict[str, Any] = search_payload([])
        self.listing_pages: dict[str, str | Exception] = {}
        self.requests: list[str] = []
        self.error: Exception | None = None

    def __call__(self, url: str, accept: str) -> str:
        self.requests.append(url)
        if self.error is not None:
            raise self.error
        if "/lrp/api/search" in url and "limit=1&" in url:
            # Taxonomy lookups (makes of "Auto's", facets of a make).
            return json.dumps(search_payload([], facets=[*CAR_FACETS, CATEGORY_FACET]))
        if "/lrp/api/search" in url:
            payload = self.payloads.pop(0) if self.payloads else self.default_payload
            return json.dumps(payload)
        if "/v/" in url:
            item_id = url.rsplit("/", 1)[-1].split("-", 1)[0]
            page = self.listing_pages.get(item_id)
            if page is None:
                page = listing_page_html(int(item_id[1:]))
            if isinstance(page, Exception):
                raise page
            return page
        return self.html


class FakeImages:
    """Returns distinct image bytes per URL; ``error`` is raised when set."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.error: Exception | None = None

    def __call__(self, url: str) -> bytes:
        self.requests.append(url)
        if self.error is not None:
            raise self.error
        return f"jpeg:{url}".encode()


class FakeAdapter:
    """In-memory platform: fixed makes/models, queued pages, chosen post-filters."""

    def __init__(
        self,
        key: str,
        label: str,
        *,
        models: dict[str, list[str]] | None = None,
        post_filters: list[str] | None = None,
    ) -> None:
        self.key = key
        self.label = label
        self._models = models or {"Tesla": ["Model 3"]}
        self._post_filters = post_filters or []
        self.pages: list[Any] = []
        self.queries: list[dict[str, Any]] = []

    def makes(self):
        from snipebot.adapters.marketplaces.base import TaxonomyOption

        return [TaxonomyOption(id=name, label=name) for name in self._models]

    def models(self, make):
        from snipebot.adapters.marketplaces.base import TaxonomyOption

        return [TaxonomyOption(id=name, label=name) for name in self._models.get(make.label, [])]

    def build_query(self, filters, seller_type):
        from snipebot.adapters.marketplaces.base import MarketplaceError, PlatformQuery

        if filters.model not in self._models.get(filters.make, []):
            raise MarketplaceError("unsupported", f"{filters.model} is not on {self.label}")
        query = {"make": filters.make, "model": filters.model, "seller": seller_type}
        for key in filters.active_keys():
            if key not in self._post_filters:
                query[key] = list(filters.bounds(key))
        return PlatformQuery(query=query, post_filters=[
            key for key in self._post_filters if key in filters.active_keys()
        ])

    def search(self, query, *, limit=None):
        from snipebot.adapters.marketplaces.base import SearchPage

        self.queries.append(query)
        page = self.pages.pop(0) if self.pages else SearchPage(0, [], complete=True)
        if isinstance(page, Exception):
            raise page
        return page


def car(
    marketplace: str,
    item_id: str,
    *,
    price: int = 30000,
    specs: dict[str, int] | None = None,
    title: str | None = None,
):
    from decimal import Decimal

    from snipebot.adapters.marketplaces.base import Listing

    return Listing(
        item_id=item_id,
        title=title or f"Tesla Model 3 {item_id}",
        description="",
        url=f"https://{marketplace}.example.test/{item_id}",
        image_url=None,
        price=Decimal(price),
        price_type=None,
        city="Lelystad",
        distance_meters=None,
        attributes={},
        seller_type=None,
        marketplace=marketplace,
        specs=specs or {},
    )


class CollectingNotifier:
    def __init__(self, ok: bool = True) -> None:
        self.messages = []
        self._ok = ok

    def send(self, message):
        self.messages.append(message)
        ok = self._ok

        class _Result:
            pass

        result = _Result()
        result.ok = ok
        result.provider_message_id = "1" if ok else None
        result.error = None if ok else "Forbidden"
        return result
