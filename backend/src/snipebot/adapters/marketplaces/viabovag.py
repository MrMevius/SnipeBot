"""ViaBOVAG.nl adapter (occasions of BOVAG-certified Dutch dealers).

Pages are Next.js App Router pages: the data is streamed in the React Server
Components "flight" format (``self.__next_f.push``). ``parse_flight`` turns it
into records: JSON values, or text blocks (``T<hex length>,``) referenced as
``$<id>``, such as a listing description.

A search page (``/auto/merk-<brand>/model-<model>[/pagina-N]``, 24 results per
page) holds ``searchResults`` with complete vehicle data: price, year, mileage,
battery capacity (Wh), specified range, license plate and the dealer with its
coordinates. Make and model lists are the ``Brand`` and ``Model`` facets.
Unknown filter paths answer HTTP 410, so SnipeBot applies all filters except
make and model itself; the values are stated, so nothing ends up "unknown".

robots.txt allows ``/auto``. Requests use the regular search cadence, a pause
between result pages and backoff when blocked.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
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
    distance_meters,
    find_option,
)
from snipebot.adapters.marketplaces.scout24 import normalize_plate

BASE_URL = "https://www.viabovag.nl"
VIABOVAG_HOSTS = {"viabovag.nl", "www.viabovag.nl"}
IMAGE_HOSTS = {"stsharedprdweu.blob.core.windows.net"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1"
PAGE_SIZE = 24
MAX_PAGES = 20
PAGE_DELAY_SECONDS = 3.0
FILTER_KEYS = ("year", "price", "mileage", "range", "battery")

_FLIGHT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.DOTALL)
_RECORD = re.compile(rb"([0-9a-f]+):")
_SLUG = re.compile(r"^[a-z0-9-]+$")

Fetcher = Callable[[str], str]


class ViaBovagError(MarketplaceError):
    """ViaBOVAG failure; ``gone`` means the listing no longer exists."""


def http_fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code in {403, 429}:
            raise ViaBovagError("blocked", f"ViaBOVAG returned HTTP {exc.code}") from exc
        if exc.code in {404, 410}:
            raise ViaBovagError("gone", "ViaBOVAG page not found") from exc
        raise ViaBovagError("fetch_error", f"ViaBOVAG returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise ViaBovagError("fetch_error", f"ViaBOVAG request failed: {exc}") from exc


def parse_flight(page_html: str) -> dict[str, Any]:
    """Records of the page's React Server Components payload, by id."""
    try:
        payload = "".join(json.loads(f'"{chunk}"') for chunk in _FLIGHT_CHUNK.findall(page_html))
    except json.JSONDecodeError as exc:
        raise ViaBovagError("parse_error", "ViaBOVAG page data is not valid") from exc
    data = payload.encode("utf-8")
    records: dict[str, Any] = {}
    position = 0
    while position < len(data):
        match = _RECORD.match(data, position)
        if match is None:
            newline = data.find(b"\n", position)
            position = len(data) if newline < 0 else newline + 1
            continue
        key = match.group(1).decode()
        position = match.end()
        if data[position : position + 1] == b"T":
            # Text block: "T<length in bytes, hex>," followed by the text itself.
            comma = data.index(b",", position)
            length = int(data[position + 1 : comma], 16)
            records[key] = data[comma + 1 : comma + 1 + length].decode("utf-8", errors="replace")
            position = comma + 1 + length
            continue
        newline = data.find(b"\n", position)
        end = len(data) if newline < 0 else newline
        try:
            records[key] = json.loads(data[position:end].decode("utf-8"))
        except ValueError:
            pass  # module references and other non-JSON rows
        position = end + 1
    return records


def find_object(value: Any, *keys: str) -> dict[str, Any] | None:
    """First dict (depth-first) that has all ``keys``."""
    if isinstance(value, dict):
        if all(key in value for key in keys):
            return value
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        found = find_object(child, *keys)
        if found is not None:
            return found
    return None


def search_props(page_html: str) -> dict[str, Any]:
    for record in parse_flight(page_html).values():
        props = find_object(record, "searchResults", "searchFacets")
        if props is not None:
            return props
    raise ViaBovagError("parse_error", "ViaBOVAG search data not found (layout change)")


def search_url(query: dict[str, Any], page: int = 1) -> str:
    brand, model = query["brand"], query["model"]
    if not (_SLUG.match(brand) and _SLUG.match(model)):
        raise ViaBovagError("invalid_filter", "Unexpected ViaBOVAG make or model")
    suffix = f"/pagina-{page}" if page > 1 else ""
    return f"{BASE_URL}/auto/merk-{brand}/model-{model}{suffix}"


def facet_options(props: dict[str, Any], name: str) -> list[TaxonomyOption]:
    facet = next(
        (item for item in (props.get("searchFacets") or {}).get("facets") or [] if item.get("name") == name),
        None,
    )
    if facet is None:
        return []
    raw = list(facet.get("options") or [])
    for category in facet.get("optionCategories") or []:
        raw.extend(category.get("options") or [])
    options: dict[str, TaxonomyOption] = {}
    for option in raw:
        key, label = option.get("name"), option.get("label")
        if isinstance(key, str) and isinstance(label, str) and key not in options:
            options[key] = TaxonomyOption(id=key, label=label)
    return list(options.values())


def parse_result(raw: Any, home: HomeLocation | None = None) -> Listing | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None
    url, title = raw.get("url"), raw.get("title")
    if not isinstance(url, str) or not isinstance(title, str):
        return None
    vehicle = raw.get("vehicle") or {}
    company = raw.get("company") or {}
    coordinates = company.get("coordinates") or {}
    price = raw.get("price")
    year, mileage = vehicle.get("year"), vehicle.get("mileage")
    battery_wh = vehicle.get("batteryCapacity")
    range_km = vehicle.get("specifiedBatteryRange")

    specs: dict[str, float] = {}
    if isinstance(year, int):
        specs["year"] = year
    if isinstance(mileage, int):
        specs["mileage"] = mileage
    if isinstance(range_km, int | float) and range_km > 0:
        specs["range"] = range_km
    if isinstance(battery_wh, int | float) and battery_wh > 0:
        specs["battery"] = round(battery_wh / 1000, 1)

    attributes = {
        key: str(value)
        for key, value in (
            ("constructionYear", year),
            ("mileage", mileage),
            ("fuel", vehicle.get("fuelType")),
            ("transmission", vehicle.get("transmissionType")),
            ("country", "NL"),
        )
        if value not in (None, "")
    }
    city = company.get("city")
    return Listing(
        item_id=raw["id"],
        title=title.strip(),
        description="",
        url=url,
        image_url=raw.get("imageUrl") if isinstance(raw.get("imageUrl"), str) else None,
        price=Decimal(int(price)) if isinstance(price, int | float) and price > 0 else None,
        price_type=None,
        city=str(city).title() if city else None,
        distance_meters=None
        if coordinates.get("isEmpty")
        else distance_meters(home, coordinates.get("latitude"), coordinates.get("longitude")),
        attributes=attributes,
        seller_type="business",
        marketplace="viabovag",
        specs=specs,
        license_plate=normalize_plate(vehicle.get("licensePlate")),
    )


class ViaBovagClient:
    def __init__(
        self,
        fetch: Fetcher | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        page_delay: float = PAGE_DELAY_SECONDS,
        home: HomeLocation | None = None,
    ) -> None:
        self._fetch = fetch or http_fetch
        self._sleep = sleep
        self._page_delay = page_delay
        self.home = home

    def props(self, url: str) -> dict[str, Any]:
        return search_props(self._fetch(url))

    def search(self, query: dict[str, Any], *, max_pages: int = MAX_PAGES) -> SearchPage:
        listings: dict[str, Listing] = {}
        total = 0
        page = 1
        while page <= max_pages:
            if page > 1:
                self._sleep(self._page_delay)
            results = self.props(search_url(query, page)).get("searchResults") or {}
            total = int(results.get("count") or 0)
            found = [
                listing
                for raw in results.get("results") or []
                if (listing := parse_result(raw, self.home)) is not None
            ]
            for listing in found:
                listings.setdefault(listing.item_id, listing)
            if not found or page * PAGE_SIZE >= total:
                break
            page += 1
        return SearchPage(
            total_count=total, listings=list(listings.values()), complete=len(listings) >= total
        )


class ViaBovagAdapter:
    """``PlatformAdapter`` for cars on ViaBOVAG.nl."""

    key = "viabovag"
    label = "ViaBOVAG"

    def __init__(
        self,
        client: ViaBovagClient | None = None,
        cache: TtlCache | None = None,
        home: HomeLocation | None = None,
    ) -> None:
        self.client = client or ViaBovagClient(home=home)
        self._cache = cache or TtlCache()

    def makes(self) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            makes = facet_options(self.client.props(f"{BASE_URL}/auto"), "Brand")
            if not makes:
                raise ViaBovagError("parse_error", "ViaBOVAG returned no car makes")
            return makes

        return self._cache.get("makes", load)

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            if not _SLUG.match(make.id):
                return []
            return facet_options(self.client.props(f"{BASE_URL}/auto/merk-{make.id}"), "Model")

        return self._cache.get(f"models:{make.id}", load)

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery:
        if seller_type == "private":
            raise ViaBovagError("unsupported", "ViaBOVAG only lists cars from BOVAG dealers")
        make = find_option(self.makes(), filters.make)
        if make is None:
            raise ViaBovagError("unsupported", f"{filters.make} is not available on ViaBOVAG")
        model = find_option(self.models(make), filters.model)
        if model is None:
            raise ViaBovagError(
                "unsupported", f"{filters.make} {filters.model} is not available on ViaBOVAG"
            )
        active = filters.active_keys()
        return PlatformQuery(
            query={"brand": make.id, "model": model.id},
            post_filters=[key for key in FILTER_KEYS if key in active],
        )

    def search(self, query: dict[str, Any], *, limit: int | None = None) -> SearchPage:
        return self.client.search(query, max_pages=1 if limit else MAX_PAGES)
