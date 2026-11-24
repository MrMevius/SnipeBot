"""Adapters for the AutoScout24 group sites: AutoTrack.nl and AutoScout24.nl.

Both sites run the same Next.js application: ``__NEXT_DATA__`` holds the result
list (``listings``, 20 per page), the make/model taxonomy and, on a listing
page, ``listingDetails``. A listing has the same id on both sites. Searches are
addressed as ``<search path>?cat=ma<make>mo<model>`` plus range parameters,
sorted newest first so a growing result set adds to the front. Neither site
filters on electric range or battery capacity; SnipeBot checks those itself.

- AutoTrack lists dealer cars in the Netherlands only. Its robots.txt disallows
  crawlers on search pages; the owner accepted this for personal use at a low
  rate. It is moving pages to a newer site without ``__NEXT_DATA__`` (in
  November 2026 only the bare ``/aanbod`` overview); such a page fails with a
  ``parse_error`` that shows on the search rather than yielding wrong results.
- AutoScout24.nl also lists private sellers and is searched in the Netherlands,
  Belgium and Germany (``cy=NL,B,D``; the owner's choice). It shows the part of
  the German offer that is advertised to Dutch buyers.

Requests use the regular search cadence, a pause between result pages and
backoff when a site blocks requests.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snipebot.adapters.marketplaces.base import (
    HomeLocation,
    Listing,
    MarketplaceError,
    PlatformQuery,
    SearchFilters,
    SearchPage,
    TaxonomyOption,
    TtlCache,
    find_option,
    power_kw,
)

IMAGE_HOSTS = {"prod.pictures.autoscout24.net"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1"
MAX_PAGES = 20
PAGE_DELAY_SECONDS = 3.0
# Resized JPEG for list thumbnails and Telegram; the archive keeps originals.
LISTING_IMAGE_SIZE = "720x540.jpg"


@dataclass(frozen=True, slots=True)
class Scout24Site:
    key: str
    label: str
    base_url: str
    hosts: frozenset[str]
    search_path: str
    listing_prefix: str
    dealers_only: bool
    # Fixed query parameters, e.g. the countries to search.
    extra_query: dict[str, str] = field(default_factory=dict)
    home_country: str = "NL"
    # The site returns distanceToSearchLocationInKm when given a postcode; a
    # radius is needed, as the default radius would drop listings.
    distance_search: bool = False


AUTOTRACK = Scout24Site(
    key="autotrack",
    label="AutoTrack",
    base_url="https://www.autotrack.nl",
    hosts=frozenset({"autotrack.nl", "www.autotrack.nl"}),
    search_path="/aanbod",
    listing_prefix="/a/",
    dealers_only=True,
)
AUTOSCOUT24 = Scout24Site(
    key="autoscout24",
    label="AutoScout24",
    base_url="https://www.autoscout24.nl",
    hosts=frozenset({"autoscout24.nl", "www.autoscout24.nl"}),
    search_path="/lst",
    listing_prefix="/aanbod/",
    dealers_only=False,
    extra_query={"cy": "NL,B,D"},
    distance_search=True,
)
DISTANCE_RADIUS_KM = 2000
SITES = {site.key: site for site in (AUTOTRACK, AUTOSCOUT24)}

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
_SELLER_TYPES = {"Dealer": "business", "Private": "private", "PrivateSeller": "private"}
_CUSTOMER_TYPES = {"private": "P", "business": "D"}

Fetcher = Callable[[str], str]


class Scout24Error(MarketplaceError):
    """AutoTrack/AutoScout24 failure; ``gone`` means the listing no longer exists."""


def http_fetch(url: str, label: str = "AutoScout24") -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code in {403, 429}:
            raise Scout24Error("blocked", f"{label} returned HTTP {exc.code}") from exc
        if exc.code in {404, 410}:
            raise Scout24Error("gone", f"{label} page not found") from exc
        raise Scout24Error("fetch_error", f"{label} returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise Scout24Error("fetch_error", f"{label} request failed: {exc}") from exc


def page_props(html: str, label: str = "AutoScout24") -> dict[str, Any]:
    match = _NEXT_DATA.search(html)
    if not match:
        raise Scout24Error("parse_error", f"{label} page data not found (unsupported page layout)")
    try:
        props = json.loads(match.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise Scout24Error("parse_error", f"{label} page data is not valid") from exc
    if not isinstance(props, dict):
        raise Scout24Error("parse_error", f"{label} page data is not valid")
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


def vehicle_title(vehicle: dict[str, Any]) -> str:
    """Make, model and version; the model is left out when the version repeats it."""
    make = str(vehicle.get("make") or "").strip()
    model = str(vehicle.get("model") or "").strip()
    version = str(vehicle.get("modelVersionInput") or "").strip()
    if model and version.lower().startswith(model.lower()):
        model = ""
    return " ".join(part for part in (make, model, version) if part)


def city_label(location: dict[str, Any], site: Scout24Site) -> str | None:
    """City, with the country code when the car is abroad ("Dilbeek (BE)")."""
    city = str(location["city"]).title() if location.get("city") else None
    country = location.get("countryCode")
    if city and country and country != site.home_country:
        return f"{city} ({country})"
    return city


class Scout24Client:
    def __init__(
        self,
        site: Scout24Site,
        fetch: Fetcher | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        page_delay: float = PAGE_DELAY_SECONDS,
        home: HomeLocation | None = None,
    ) -> None:
        self.site = site
        self.home = home
        self._fetch = fetch or (lambda url: http_fetch(url, site.label))
        self._sleep = sleep
        self._page_delay = page_delay

    def props(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.site.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return page_props(self._fetch(url), self.site.label)

    def search(self, query: dict[str, Any], *, max_pages: int = MAX_PAGES) -> SearchPage:
        listings: dict[str, Listing] = {}
        total = 0
        page_count = 1
        page = 1
        distance: dict[str, Any] = {}
        if self.site.distance_search and self.home is not None and self.home.postcode:
            distance = {
                "zip": self.home.postcode,
                "zipc": self.home.country,
                "zipr": DISTANCE_RADIUS_KM,
            }
        while page <= min(page_count, max_pages):
            if page > 1:
                self._sleep(self._page_delay)
            props = self.props(
                self.site.search_path,
                {**query, **distance, "sort": "age", "desc": "1", "page": page},
            )
            raw_listings = props.get("listings")
            if not isinstance(raw_listings, list):
                raise Scout24Error("parse_error", f"{self.site.label} search page has no listings")
            total = int(props.get("numberOfResults") or 0)
            page_count = int(props.get("numberOfPages") or 1)
            for raw in raw_listings:
                listing = parse_listing(raw, self.site)
                if listing is not None:
                    # Pages can overlap when listings are added while paging.
                    listings.setdefault(listing.item_id, listing)
            page += 1
        return SearchPage(
            total_count=total,
            listings=list(listings.values()),
            complete=len(listings) >= total,
        )


class Scout24Adapter:
    """``PlatformAdapter`` for cars on an AutoScout24 group site."""

    def __init__(
        self,
        site: Scout24Site,
        client: Scout24Client | None = None,
        cache: TtlCache | None = None,
        home: HomeLocation | None = None,
    ) -> None:
        self.site = site
        self.key = site.key
        self.label = site.label
        self.client = client or Scout24Client(site, home=home)
        self._cache = cache or TtlCache()

    def makes(self) -> list[TaxonomyOption]:
        return self._cache.get("makes", self._load_makes)

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            props = self.client.props(self.site.search_path, {"cat": f"ma{make.id}"})
            taxonomy = props.get("taxonomy") or {}
            return [
                TaxonomyOption(id=str(item["value"]), label=str(item["label"]))
                for item in (taxonomy.get("models") or {}).get(make.id) or []
                if item.get("value") is not None and item.get("label")
            ]

        return self._cache.get(f"models:{make.id}", load)

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery:
        label = self.site.label
        if seller_type == "private" and self.site.dealers_only:
            raise Scout24Error("unsupported", f"{label} only lists cars from dealers")
        make = find_option(self.makes(), filters.make)
        if make is None:
            raise Scout24Error("unsupported", f"{filters.make} is not available on {label}")
        model = find_option(self.models(make), filters.model)
        if model is None:
            raise Scout24Error(
                "unsupported", f"{filters.make} {filters.model} is not available on {label}"
            )
        query: dict[str, Any] = {"cat": f"ma{make.id}mo{model.id}", **self.site.extra_query}
        if seller_type in _CUSTOMER_TYPES and not self.site.dealers_only:
            query["custtype"] = _CUSTOMER_TYPES[seller_type]
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
        # A bare search page may use AutoTrack's newer site without page data;
        # any filtered search page carries the full make list.
        taxonomy = self.client.props(self.site.search_path, {"atype": "C"}).get("taxonomy") or {}
        makes = [
            TaxonomyOption(id=str(item["value"]), label=str(item["label"]))
            for item in taxonomy.get("makesSorted") or []
            if item.get("value") is not None and item.get("label")
        ]
        if not makes:
            raise Scout24Error("parse_error", f"{self.site.label} returned no car makes")
        return makes


def parse_listing(raw: Any, site: Scout24Site) -> Listing | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None
    path = raw.get("url")
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    vehicle = raw.get("vehicle") or {}
    tracking = raw.get("tracking") or {}
    title = vehicle_title(vehicle) or str(raw.get("title") or "").strip()
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
        if isinstance(detail, dict) and detail.get("iconName") == "speedometer":
            if (kw := power_kw(detail.get("data"))) is not None:
                specs["power"] = kw
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
    if location.get("countryCode"):
        attributes["country"] = str(location["countryCode"])
    distance_km = location.get("distanceToSearchLocationInKm")
    return Listing(
        item_id=raw["id"],
        title=title,
        description="",
        url=f"{site.base_url}{path}",
        image_url=f"{original_image_url(images[0])}/{LISTING_IMAGE_SIZE}" if images else None,
        price=Decimal(int(price_raw)) if isinstance(price_raw, int) and price_raw > 0 else None,
        price_type=None,
        city=str(location["city"]).title() if location.get("city") else None,
        distance_meters=round(distance_km * 1000) if isinstance(distance_km, int | float) else None,
        attributes=attributes,
        seller_type=_SELLER_TYPES.get(str((raw.get("seller") or {}).get("type"))),
        marketplace=site.key,
        specs=specs,
        license_plate=normalize_plate((vehicle.get("jsonLd") or {}).get("licensePlate")),
    )
