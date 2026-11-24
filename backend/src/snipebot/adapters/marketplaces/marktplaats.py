"""Marktplaats.nl saved-search adapter.

A pasted search URL has two parts. The path (category, SEO filters, query) is
resolved by Marktplaats itself: the result page embeds the search request it
derived from the path. The ``#`` fragment (ranges, postcode, extra attribute
ids) never reaches the server, so it is parsed here using the same rules as the
Marktplaats web client. The combined request is then run against the JSON
search endpoint the web client uses.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

BASE_URL = "https://www.marktplaats.nl"
SEARCH_API_URL = f"{BASE_URL}/lrp/api/search"
MARKTPLAATS_HOSTS = {"marktplaats.nl", "www.marktplaats.nl"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1"
PAGE_LIMIT = 100
SELLER_TYPES = ("all", "private", "business")

_ADVERTISER_VALUES = {"private": "Particulier", "business": "Bedrijf"}
_SELLER_TYPE_BY_ADVERTISER = {value: key for key, value in _ADVERTISER_VALUES.items()}
_NEXT_DATA = re.compile(
    r"<script\b[^>]*\bid=\"__NEXT_DATA__\"[^>]*>(.*?)</script\s*>", re.DOTALL
)
_RANGE_KEY = re.compile(r"^(.+)(From|To)$")
_ITEM_ID = re.compile(r"^m(\d+)$")
_IGNORED_FRAGMENT_KEYS = {
    "sortBy",
    "sortOrder",
    "sortAttribute",
    "view",
    "limit",
    "offset",
    "asSavedSearch",
    "bypassSpellingSuggestion",
    "traits",
}
_RANGE_LABEL_FALLBACKS = {"PriceCents": "Prijs"}

Fetcher = Callable[[str, str], str]


class MarktplaatsError(Exception):
    """Raised for invalid search URLs and failed or unparsable responses.

    ``kind`` is one of ``invalid_url``, ``fetch_error``, ``blocked``,
    ``parse_error`` or ``gone`` (HTTP 410 for a removed listing).
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(slots=True)
class AttributeRange:
    key: str
    low: int | None = None
    high: int | None = None


@dataclass(slots=True)
class SearchQuery:
    query: str | None = None
    l1_category_id: int | None = None
    l2_category_ids: list[int] = field(default_factory=list)
    attribute_ids: list[int] = field(default_factory=list)
    attributes_by_key: list[str] = field(default_factory=list)
    ranges: list[AttributeRange] = field(default_factory=list)
    postcode: str | None = None
    distance_meters: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchQuery:
        return cls(
            query=payload.get("query"),
            l1_category_id=payload.get("l1_category_id"),
            l2_category_ids=list(payload.get("l2_category_ids") or []),
            attribute_ids=list(payload.get("attribute_ids") or []),
            attributes_by_key=list(payload.get("attributes_by_key") or []),
            ranges=[AttributeRange(**item) for item in payload.get("ranges") or []],
            postcode=payload.get("postcode"),
            distance_meters=payload.get("distance_meters"),
        )

    def api_params(self, *, limit: int = PAGE_LIMIT) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        if self.query:
            params.append(("query", self.query))
        if self.l1_category_id is not None:
            params.append(("l1CategoryId", str(self.l1_category_id)))
        params.extend(("l2CategoryIds[]", str(value)) for value in self.l2_category_ids)
        params.extend(("attributesById[]", str(value)) for value in self.attribute_ids)
        params.extend(("attributesByKey[]", value) for value in self.attributes_by_key)
        for item in self.ranges:
            params.append(
                ("attributeRanges[]", f"{item.key}:{_range_bound(item.low)}:{_range_bound(item.high)}")
            )
        if self.postcode:
            params.append(("postcode", self.postcode))
            if self.distance_meters:
                params.append(("distanceMeters", str(self.distance_meters)))
        params.extend(
            [
                ("limit", str(limit)),
                ("offset", "0"),
                ("sortBy", "SORT_INDEX"),
                ("sortOrder", "DECREASING"),
                ("viewOptions", "list-view"),
            ]
        )
        return params


@dataclass(slots=True)
class ResolvedSearch:
    query: SearchQuery
    category_names: list[str]
    warnings: list[str]


@dataclass(slots=True)
class Listing:
    item_id: str
    title: str
    description: str
    url: str
    image_url: str | None
    price: Decimal | None
    price_type: str | None
    city: str | None
    distance_meters: int | None
    attributes: dict[str, str]
    seller_type: str | None

    @property
    def numeric_id(self) -> int | None:
        match = _ITEM_ID.match(self.item_id)
        return int(match.group(1)) if match else None


@dataclass(slots=True)
class SearchPage:
    total_count: int
    listings: list[Listing]
    facets: list[dict[str, Any]]


def validate_search_url(url: str) -> tuple[str, str]:
    """Return the canonical path URL and the raw fragment of a search URL."""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or parts.hostname not in MARKTPLAATS_HOSTS:
        raise MarktplaatsError("invalid_url", "Use a search URL from marktplaats.nl")
    path = parts.path or "/"
    if not (path.startswith("/l/") or path.startswith("/q/")):
        raise MarktplaatsError(
            "invalid_url",
            "Use a Marktplaats search results URL (marktplaats.nl/l/... or /q/...)",
        )
    canonical = f"{BASE_URL}{path}"
    if parts.query:
        canonical = f"{canonical}?{parts.query}"
    return canonical, parts.fragment


def query_from_page_html(html: str) -> tuple[SearchQuery, list[str]]:
    match = _NEXT_DATA.search(html)
    if not match:
        raise MarktplaatsError("parse_error", "Search page data not found")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise MarktplaatsError("parse_error", "Search page data is not valid JSON") from exc

    search = _find_key(data, "searchRequestAndResponse")
    if not isinstance(search, dict) or not isinstance(search.get("searchRequest"), dict):
        raise MarktplaatsError("parse_error", "Search request not found in page data")
    request = search["searchRequest"].get("originalRequest") or search["searchRequest"]

    categories = request.get("categories") or {}
    l1 = categories.get("l1Category") or {}
    l2_list = categories.get("l2Categories") or []
    names = [str(l1["fullName"])] if l1.get("fullName") else []
    names.extend(str(item["fullName"]) for item in l2_list if item.get("fullName"))

    attributes_by_key: list[str] = []
    for item in request.get("attributesByKey") or []:
        if isinstance(item, dict) and item.get("attributeKey"):
            attributes_by_key.append(f"{item['attributeKey']}:{item.get('attributeValueKey', '')}")
        elif isinstance(item, str):
            attributes_by_key.append(item)

    distance = request.get("distance") or {}
    query = SearchQuery(
        query=request.get("searchQuery") or None,
        l1_category_id=l1.get("id"),
        l2_category_ids=[int(item["id"]) for item in l2_list if item.get("id") is not None],
        attribute_ids=[int(value) for value in request.get("attributesById") or []],
        attributes_by_key=attributes_by_key,
        ranges=[
            AttributeRange(
                key=str(item["attributeKey"]),
                low=_as_int(item.get("from")),
                high=_as_int(item.get("to")),
            )
            for item in request.get("attributeRanges") or []
            if isinstance(item, dict) and item.get("attributeKey")
        ],
        postcode=distance.get("postcode") or None,
        distance_meters=_as_int(distance.get("distanceMeters")) or None,
    )
    return query, names


def apply_fragment(query: SearchQuery, fragment: str) -> list[str]:
    """Merge the browser-only ``#`` filters into ``query``; return warnings."""
    warnings: list[str] = []
    for part in unquote(fragment).lstrip("#").split("|"):
        pieces = part.split(":")
        if len(pieces) < 2 or not pieces[0] or not pieces[1]:
            continue
        key, value = pieces[0], pieces[1]

        range_match = _RANGE_KEY.match(key)
        if range_match:
            number = _as_int(value)
            if number is None:
                warnings.append(f"Ignored filter {key}:{value}")
                continue
            _set_range_bound(query, range_match.group(1), range_match.group(2), number)
        elif key == "q":
            query.query = " ".join(value.split("+")).strip() or None
        elif key == "f":
            for raw_id in value.split(","):
                number = _as_int(raw_id)
                if number is not None and number not in query.attribute_ids:
                    query.attribute_ids.append(number)
        elif key == "offeredSince":
            _add_attribute_by_key(query, f"offeredSince:{value}")
        elif key == "ta":
            for group in value.split("~"):
                attr_key, _, values = group.partition("=")
                for attr_value in values.split(","):
                    if attr_key and attr_value:
                        _add_attribute_by_key(query, f"{attr_key}:{attr_value}")
        elif key == "postcode":
            query.postcode = value.replace(" ", "").upper() or None
        elif key == "distanceMeters":
            query.distance_meters = _as_int(value) or None
        elif key not in _IGNORED_FRAGMENT_KEYS:
            warnings.append(f"Ignored unknown filter {key}:{value}")
    return warnings


def apply_seller_type(
    query: SearchQuery, seller_type: str, facets: list[dict[str, Any]]
) -> SearchQuery:
    """Return a copy of ``query`` restricted to the chosen advertiser type.

    ``all`` keeps whatever advertiser filter the pasted URL already has.
    """
    if seller_type not in SELLER_TYPES:
        raise MarktplaatsError("invalid_url", f"Unknown seller type: {seller_type}")
    result = SearchQuery.from_dict(query.to_dict())
    if seller_type == "all":
        return result

    advertiser = _find_facet(facets, "advertiser")
    value_ids = {
        str(item.get("attributeValueKey")): int(item["attributeValueId"])
        for item in (advertiser or {}).get("attributeGroup") or []
        if item.get("attributeValueId") is not None
    }
    result.attribute_ids = [
        value for value in result.attribute_ids if value not in value_ids.values()
    ]
    wanted = value_ids.get(_ADVERTISER_VALUES[seller_type])
    if wanted is None:
        raise MarktplaatsError(
            "invalid_url",
            "This Marktplaats category does not support filtering on seller type",
        )
    result.attribute_ids.append(wanted)
    return result


def parse_search_response(payload: dict[str, Any]) -> SearchPage:
    listings_raw = payload.get("listings")
    if not isinstance(listings_raw, list):
        raise MarktplaatsError("parse_error", "Search response has no listings")
    listings = [listing for raw in listings_raw if (listing := parse_listing(raw))]
    facets = payload.get("facets")
    return SearchPage(
        total_count=int(payload.get("totalResultCount") or 0),
        listings=listings,
        facets=facets if isinstance(facets, list) else [],
    )


def parse_listing(raw: Any) -> Listing | None:
    if not isinstance(raw, dict):
        return None
    item_id = raw.get("itemId")
    title = raw.get("title")
    vip_url = raw.get("vipUrl")
    if not isinstance(item_id, str) or not isinstance(title, str) or not isinstance(vip_url, str):
        return None

    attributes: dict[str, str] = {}
    for group in ("attributes", "extendedAttributes"):
        for item in raw.get(group) or []:
            if isinstance(item, dict) and item.get("key") and item.get("value") is not None:
                attributes.setdefault(str(item["key"]), str(item["value"]))

    price_info = raw.get("priceInfo") or {}
    price_cents = _as_int(price_info.get("priceCents"))
    location = raw.get("location") or {}
    distance = _as_int(location.get("distanceMeters"))

    return Listing(
        item_id=item_id,
        title=title.strip(),
        description=str(raw.get("description") or ""),
        url=vip_url if vip_url.startswith("http") else f"{BASE_URL}{vip_url}",
        image_url=_listing_image(raw),
        price=Decimal(price_cents) / 100 if price_cents and price_cents > 0 else None,
        price_type=price_info.get("priceType"),
        city=location.get("cityName") or None,
        distance_meters=distance if distance is not None and distance >= 0 else None,
        attributes=attributes,
        seller_type=_SELLER_TYPE_BY_ADVERTISER.get(attributes.get("advertiser", "")),
    )


def describe_query(
    query: SearchQuery, facets: list[dict[str, Any]], category_names: list[str]
) -> list[str]:
    """Human-readable (Dutch) summary of what the search filters on."""
    lines: list[str] = []
    if category_names:
        lines.append(f"Categorie: {' › '.join(category_names)}")
    if query.query:
        lines.append(f"Zoekterm: {query.query}")

    value_labels: dict[int, tuple[str, str]] = {}
    for facet in facets:
        for item in facet.get("attributeGroup") or []:
            if item.get("attributeValueId") is not None:
                value_labels[int(item["attributeValueId"])] = (
                    str(facet.get("label") or facet.get("key")),
                    str(item.get("attributeValueLabel") or item.get("attributeValueKey")),
                )
    grouped: dict[str, list[str]] = {}
    for value_id in query.attribute_ids:
        label, value = value_labels.get(value_id, ("Filter", f"#{value_id}"))
        grouped.setdefault(label, []).append(value)
    lines.extend(f"{label}: {', '.join(values)}" for label, values in grouped.items())

    for item in query.attributes_by_key:
        key, _, value = item.partition(":")
        facet = _find_facet(facets, key)
        lines.append(f"{(facet or {}).get('label') or key}: {value}")

    for item in query.ranges:
        facet = _find_facet(facets, item.key)
        label = (facet or {}).get("label") or _RANGE_LABEL_FALLBACKS.get(item.key, item.key)
        low = _format_range_value(item.key, item.low)
        high = _format_range_value(item.key, item.high)
        if low and high:
            lines.append(f"{label}: {low} t/m {high}")
        elif low:
            lines.append(f"{label}: vanaf {low}")
        elif high:
            lines.append(f"{label}: t/m {high}")

    if query.postcode:
        if query.distance_meters:
            lines.append(
                f"Afstand: binnen {query.distance_meters // 1000} km van {query.postcode}"
            )
        else:
            lines.append(f"Postcode: {query.postcode}")
    return lines


class MarktplaatsClient:
    def __init__(self, fetch: Fetcher | None = None) -> None:
        self._fetch = fetch or _http_fetch

    def resolve(self, url: str) -> ResolvedSearch:
        page_url, fragment = validate_search_url(url)
        html = self._fetch(page_url, "text/html")
        query, names = query_from_page_html(html)
        warnings = apply_fragment(query, fragment)
        return ResolvedSearch(query=query, category_names=names, warnings=warnings)

    def search(self, query: SearchQuery, *, limit: int = PAGE_LIMIT) -> SearchPage:
        url = f"{SEARCH_API_URL}?{urlencode(query.api_params(limit=limit))}"
        body = self._fetch(url, "application/json")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise MarktplaatsError("parse_error", "Search response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise MarktplaatsError("parse_error", "Unexpected search response")
        return parse_search_response(payload)


def _http_fetch(url: str, accept: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        kind = "blocked" if exc.code in {403, 429} else "fetch_error"
        if exc.code == 404:
            raise MarktplaatsError("invalid_url", "Marktplaats page not found") from exc
        if exc.code == 410:
            raise MarktplaatsError("gone", "Marktplaats listing was removed") from exc
        raise MarktplaatsError(kind, f"Marktplaats returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise MarktplaatsError("fetch_error", f"Marktplaats request failed: {exc}") from exc


def _listing_image(raw: dict[str, Any]) -> str | None:
    pictures = raw.get("pictures")
    if isinstance(pictures, list) and pictures and isinstance(pictures[0], dict):
        for key in ("extraExtraLargeUrl", "largeUrl", "mediumUrl"):
            value = pictures[0].get(key)
            if isinstance(value, str) and value:
                return value
    image_urls = raw.get("imageUrls")
    if isinstance(image_urls, list) and image_urls and isinstance(image_urls[0], str):
        return f"https:{image_urls[0]}" if image_urls[0].startswith("//") else image_urls[0]
    return None


def _find_key(data: Any, key: str) -> Any:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        values = data.values()
    elif isinstance(data, list):
        values = data
    else:
        return None
    for value in values:
        found = _find_key(value, key)
        if found is not None:
            return found
    return None


def _find_facet(facets: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((facet for facet in facets if facet.get("key") == key), None)


def _set_range_bound(query: SearchQuery, key: str, side: str, value: int) -> None:
    existing = next((item for item in query.ranges if item.key == key), None)
    if existing is None:
        existing = AttributeRange(key=key)
        query.ranges.append(existing)
    if side == "From":
        existing.low = value
    else:
        existing.high = value


def _add_attribute_by_key(query: SearchQuery, value: str) -> None:
    if value not in query.attributes_by_key:
        query.attributes_by_key.append(value)


def _range_bound(value: int | None) -> str:
    return "null" if value is None else str(value)


def _format_range_value(key: str, value: int | None) -> str | None:
    if value is None:
        return None
    if key == "PriceCents":
        return f"€ {_thousands(value // 100)}"
    if key == "mileage":
        return f"{_thousands(value)} km"
    return str(value)


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None
