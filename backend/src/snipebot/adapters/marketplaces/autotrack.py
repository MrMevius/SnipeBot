"""AutoTrack.nl adapter (an AutoScout24 site).

Search and listing pages are Next.js pages: ``__NEXT_DATA__`` holds the result
list (``listings``, 20 per page), the make/model taxonomy and, on a listing
page, ``listingDetails``. Searches are addressed as ``/aanbod?cat=ma<make>mo<model>``
plus range parameters, sorted newest first so a growing result set adds to the
front. AutoTrack lists dealer cars only and cannot filter on electric range or
battery capacity; SnipeBot checks those itself.

AutoTrack's robots.txt disallows crawlers on search pages. The owner accepted
this for personal use at a low rate: the regular search cadence, a pause
between result pages and backoff when AutoTrack blocks requests.

AutoTrack is moving pages to a newer site without ``__NEXT_DATA__`` (in
November 2026 only the bare ``/aanbod`` overview). Such a page fails with a
``parse_error`` that shows on the search, rather than yielding wrong results.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snipebot.adapters.marketplaces.base import (
    Listing,
    MarketplaceError,
    PlatformQuery,
    SearchFilters,
    SearchPage,
    TaxonomyOption,
    TtlCache,
    find_option,
)

BASE_URL = "https://www.autotrack.nl"
AUTOTRACK_HOSTS = {"autotrack.nl", "www.autotrack.nl"}
IMAGE_HOSTS = {"prod.pictures.autoscout24.net"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1"
MAX_PAGES = 20
PAGE_DELAY_SECONDS = 3.0
# Resized JPEG for list thumbnails and Telegram; the archive keeps originals.
LISTING_IMAGE_SIZE = "720x540.jpg"

_NEXT_DATA = re.compile(
    r"<script\b[^>]*\bid=\"__NEXT_DATA__\"[^>]*>(.*?)</script\s*>", re.DOTALL
)
_IMAGE_SIZE_SUFFIX = re.compile(r"(\.jpe?g)/[^/]+$", re.IGNORECASE)
_BATTERY = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*kwh(?!\s*/)", re.IGNORECASE)
_NUMBER = re.compile(r"\d+")
_QUERY_PARAMS = {
    "year": ("fregfrom", "fregto"),
    "price": ("pricefrom", "priceto"),
    "mileage": ("kmfrom", "kmto"),
}
_POST_FILTERS = ("range", "battery")
_SELLER_TYPES = {"Dealer": "business", "Private": "private"}

Fetcher = Callable[[str], str]


class AutoTrackError(MarketplaceError):
    """AutoTrack failure; ``gone`` means the listing no longer exists."""


def http_fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code in {403, 429}:
            raise AutoTrackError("blocked", f"AutoTrack returned HTTP {exc.code}") from exc
        if exc.code in {404, 410}:
            raise AutoTrackError("gone", "AutoTrack page not found") from exc
        raise AutoTrackError("fetch_error", f"AutoTrack returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise AutoTrackError("fetch_error", f"AutoTrack request failed: {exc}") from exc


def page_props(html: str) -> dict[str, Any]:
    match = _NEXT_DATA.search(html)
    if not match:
        raise AutoTrackError(
            "parse_error", "AutoTrack page data not found (unsupported page layout)"
        )
    try:
        props = json.loads(match.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AutoTrackError("parse_error", "AutoTrack page data is not valid") from exc
    if not isinstance(props, dict):
        raise AutoTrackError("parse_error", "AutoTrack page data is not valid")
    return props


def original_image_url(url: str) -> str:
    """Drop the size suffix (``.../<name>.jpg/1280x960.webp``): the uploaded JPEG."""
    return _IMAGE_SIZE_SUFFIX.sub(r"\1", url)


def normalize_plate(value: Any) -> str | None:
    plate = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return plate if 4 <= len(plate) <= 8 else None


def battery_kwh(text: str) -> float | None:
    """Battery capacity from free text such as "Long Range 75 kWh" (not kWh/100 km)."""
    match = _BATTERY.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 10 <= value <= 250 else None


class AutoTrackClient:
    def __init__(
        self,
        fetch: Fetcher | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        page_delay: float = PAGE_DELAY_SECONDS,
    ) -> None:
        self._fetch = fetch or http_fetch
        self._sleep = sleep
        self._page_delay = page_delay

    def props(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return page_props(self._fetch(url))

    def search(self, query: dict[str, Any], *, max_pages: int = MAX_PAGES) -> SearchPage:
        listings: dict[str, Listing] = {}
        total = 0
        page_count = 1
        page = 1
        while page <= min(page_count, max_pages):
            if page > 1:
                self._sleep(self._page_delay)
            props = self.props("/aanbod", {**query, "sort": "age", "desc": "1", "page": page})
            raw_listings = props.get("listings")
            if not isinstance(raw_listings, list):
                raise AutoTrackError("parse_error", "AutoTrack search page has no listings")
            total = int(props.get("numberOfResults") or 0)
            page_count = int(props.get("numberOfPages") or 1)
            for raw in raw_listings:
                listing = parse_listing(raw)
                if listing is not None:
                    # Pages can overlap when listings are added while paging.
                    listings.setdefault(listing.item_id, listing)
            page += 1
        return SearchPage(
            total_count=total,
            listings=list(listings.values()),
            complete=len(listings) >= total,
        )


class AutoTrackAdapter:
    """``PlatformAdapter`` for cars on AutoTrack.nl."""

    key = "autotrack"
    label = "AutoTrack"

    def __init__(self, client: AutoTrackClient | None = None, cache: TtlCache | None = None):
        self.client = client or AutoTrackClient()
        self._cache = cache or TtlCache()

    def makes(self) -> list[TaxonomyOption]:
        return self._cache.get("makes", self._load_makes)

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            taxonomy = self.client.props("/aanbod", {"cat": f"ma{make.id}"}).get("taxonomy") or {}
            return [
                TaxonomyOption(id=str(item["value"]), label=str(item["label"]))
                for item in (taxonomy.get("models") or {}).get(make.id) or []
                if item.get("value") is not None and item.get("label")
            ]

        return self._cache.get(f"models:{make.id}", load)

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery:
        if seller_type == "private":
            raise AutoTrackError("unsupported", "AutoTrack only lists cars from dealers")
        make = find_option(self.makes(), filters.make)
        if make is None:
            raise AutoTrackError("unsupported", f"{filters.make} is not available on AutoTrack")
        model = find_option(self.models(make), filters.model)
        if model is None:
            raise AutoTrackError(
                "unsupported", f"{filters.make} {filters.model} is not available on AutoTrack"
            )
        query: dict[str, Any] = {"cat": f"ma{make.id}mo{model.id}"}
        for key, (low_param, high_param) in _QUERY_PARAMS.items():
            low, high = filters.bounds(key)
            if low is not None:
                query[low_param] = low
            if high is not None:
                query[high_param] = high
        active = filters.active_keys()
        return PlatformQuery(query=query, post_filters=[key for key in _POST_FILTERS if key in active])

    def search(self, query: dict[str, Any], *, limit: int | None = None) -> SearchPage:
        return self.client.search(query, max_pages=1 if limit else MAX_PAGES)

    def _load_makes(self) -> list[TaxonomyOption]:
        # The bare /aanbod page uses AutoTrack's newer site without page data;
        # any filtered search page carries the full make list.
        taxonomy = self.client.props("/aanbod", {"atype": "C"}).get("taxonomy") or {}
        makes = [
            TaxonomyOption(id=str(item["value"]), label=str(item["label"]))
            for item in taxonomy.get("makesSorted") or []
            if item.get("value") is not None and item.get("label")
        ]
        if not makes:
            raise AutoTrackError("parse_error", "AutoTrack returned no car makes")
        return makes


def parse_listing(raw: Any) -> Listing | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None
    path = raw.get("url")
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    vehicle = raw.get("vehicle") or {}
    tracking = raw.get("tracking") or {}
    title = " ".join(
        str(part).strip()
        for part in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput"))
        if part
    ) or str(raw.get("title") or "").strip()
    if not title:
        return None

    price_raw = (raw.get("price") or {}).get("priceRaw")
    images = [url for url in raw.get("images") or [] if isinstance(url, str)]
    first_registration = str(tracking.get("firstRegistration") or "")
    year = first_registration[-4:] if re.fullmatch(r"\d{2}-\d{4}", first_registration) else None
    mileage = str(tracking.get("mileage") or "")

    specs: dict[str, float] = {}
    if year:
        specs["year"] = int(year)
    if mileage.isdigit():
        specs["mileage"] = int(mileage)
    for detail in raw.get("vehicleDetails") or []:
        if isinstance(detail, dict) and detail.get("iconName") == "distance":
            number = _NUMBER.search(str(detail.get("data") or "").replace(".", ""))
            if number:
                specs["range"] = int(number.group(0))
    battery = battery_kwh(title)
    if battery is not None:
        specs["battery"] = battery

    attributes = {
        key: str(value)
        for key, value in (
            ("constructionYear", year),
            ("mileage", mileage if mileage.isdigit() else None),
            ("fuel", vehicle.get("fuel")),
            ("transmission", vehicle.get("transmission")),
        )
        if value
    }
    location = raw.get("location") or {}
    city = location.get("city")
    return Listing(
        item_id=raw["id"],
        title=title,
        description="",
        url=f"{BASE_URL}{path}",
        image_url=f"{original_image_url(images[0])}/{LISTING_IMAGE_SIZE}" if images else None,
        price=Decimal(int(price_raw)) if isinstance(price_raw, int) and price_raw > 0 else None,
        price_type=None,
        city=str(city).title() if city else None,
        distance_meters=None,
        attributes=attributes,
        seller_type=_SELLER_TYPES.get(str((raw.get("seller") or {}).get("type"))),
        marketplace="autotrack",
        specs=specs,
        license_plate=normalize_plate((vehicle.get("jsonLd") or {}).get("licensePlate")),
    )
