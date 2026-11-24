"""Kleinanzeigen.de adapter (German classifieds; private sellers and dealers).

Search pages are Astro pages. Their ``astro-island`` components carry props in
Astro's serialized form (``[type, value]`` pairs, see ``island_props``):

- ``ImpressionTracker`` holds ``resultAds`` with each listing's id, title, price
  ("25.200 € VB"), seller type, postcode, place, photos and the attributes
  "70.810 km" and "EZ 08/2020". Paid "top ads" are left out: they are shown on
  every page and do not have to match the search (a Model Y in a Model 3
  search).
- Menu items (in ``FilterChips``' browse menus and, for long lists, a
  ``SearchableMenuItems`` island) list the makes (``/s-autos/c216``) or the
  models of a make (``/s-autos/<make>/c216+autos.marke_s:<make>``); an item's
  URL ends with the ``autos.marke_s``/``autos.model_s`` filter it selects.

A search URL holds the make, model, price, first registration year, mileage,
seller type, page (25 results, the site serves at most 50 pages) and the
newest-first order. Kleinanzeigen has no range or battery filter, so SnipeBot
checks those itself; battery capacity only comes from the title or the start
of the description, range is never stated.

Python's own HTTP client is refused with HTTP 403; requests use curl with
SnipeBot's regular user agent. robots.txt allows ``/s-autos/`` and
``/s-anzeige/``. Requests use the regular search cadence, a pause between
result pages and backoff when blocked.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.parse import quote

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
from snipebot.adapters.marketplaces.scout24 import battery_kwh

BASE_URL = "https://www.kleinanzeigen.de"
KLEINANZEIGEN_HOSTS = {"kleinanzeigen.de", "www.kleinanzeigen.de"}
IMAGE_HOSTS = {"img.kleinanzeigen.de"}
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1"
CATEGORY = "c216"
PAGE_SIZE = 25
MAX_PAGES = 20
PAGE_DELAY_SECONDS = 3.0
REQUEST_TIMEOUT_SECONDS = 20
# Sellers state "1 € VB" for "price on request"; such amounts are no price, so
# they never fall under an alert price ceiling.
MIN_PRICE = 100
# Kleinanzeigen filters year, price and mileage itself.
POST_FILTER_KEYS = ("range", "battery")
_POSTER = {"private": "privat", "business": "gewerblich"}
_SELLER_TYPES = {"PRIVATE": "private", "COMMERCIAL": "business"}

_ISLAND = re.compile(r"<astro-island\b[^>]*>")
_ATTRIBUTE = re.compile(r'([a-z-]+)="([^"]*)"')
_SLUG = re.compile(r"^[a-z0-9_]+$")
_PRICE = re.compile(r"^([\d.]+)\s*€")
_MILEAGE = re.compile(r"^([\d.]+)\s*km$")
_REGISTRATION = re.compile(r"^EZ\s+(?:\d{1,2}/)?(\d{4})$")

Fetcher = Callable[[str], str]


class KleinanzeigenError(MarketplaceError):
    """Kleinanzeigen failure; ``gone`` means the listing no longer exists."""


def curl(url: str, *, accept: str = "text/html", max_bytes: int | None = None) -> bytes:
    """GET ``url`` with curl; redirects are not followed (a removed ad redirects)."""
    command = [
        "curl", "--disable", "--globoff", "--silent", "--show-error", "--compressed",
        "--max-time", str(REQUEST_TIMEOUT_SECONDS),
        "--user-agent", USER_AGENT,
        "--header", f"Accept: {accept}",
        "--header", "Accept-Language: de-DE,de;q=0.9",
        "--write-out", "\n%{http_code}",
    ]
    if max_bytes is not None:
        command += ["--max-filesize", str(max_bytes)]
    try:
        result = subprocess.run(
            [*command, "--url", url],
            capture_output=True,
            check=False,
            timeout=REQUEST_TIMEOUT_SECONDS + 5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KleinanzeigenError("fetch_error", f"Kleinanzeigen request failed: {exc}") from exc
    if result.returncode == 63:
        raise KleinanzeigenError("fetch_error", "Kleinanzeigen response is too large")
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise KleinanzeigenError(
            "fetch_error", f"Kleinanzeigen request failed: {message or f'curl {result.returncode}'}"
        )
    body, _, status_line = result.stdout.rpartition(b"\n")
    status = int(status_line or 0)
    if status in {403, 429}:
        raise KleinanzeigenError("blocked", f"Kleinanzeigen returned HTTP {status}")
    if status in {301, 302, 404, 410}:
        raise KleinanzeigenError("gone", "Kleinanzeigen page not found")
    if status != 200:
        raise KleinanzeigenError("fetch_error", f"Kleinanzeigen returned HTTP {status}")
    return body


def http_fetch(url: str) -> str:
    return curl(url).decode("utf-8", errors="replace")


def _revive(value: Any) -> Any:
    """Undo Astro's prop serialization: ``[0, value]`` plain, ``[1, [...]]`` array."""
    if isinstance(value, list):
        if len(value) == 2 and isinstance(value[0], int):
            kind, inner = value
            if kind == 1 and isinstance(inner, list):
                return [_revive(item) for item in inner]
            if kind == 0 and isinstance(inner, dict):
                return {key: _revive(item) for key, item in inner.items()}
            return inner
        return [_revive(item) for item in value]
    if isinstance(value, dict):
        return {key: _revive(item) for key, item in value.items()}
    return value


def island_props(page_html: str) -> list[tuple[str, dict[str, Any]]]:
    """(component name, props) of the page's Astro islands, in page order."""
    islands: list[tuple[str, dict[str, Any]]] = []
    for tag in _ISLAND.finditer(page_html):
        attributes = dict(_ATTRIBUTE.findall(tag.group(0)))
        name = attributes.get("component-url", "").rsplit("/", 1)[-1].split(".", 1)[0]
        if not name or "props" not in attributes:
            continue
        try:
            props = _revive(json.loads(html.unescape(attributes["props"])))
        except ValueError:
            continue
        if isinstance(props, dict):
            islands.append((name, props))
    return islands


def _range(bounds: tuple[int | None, int | None]) -> str | None:
    low, high = bounds
    if low is None and high is None:
        return None
    return f"{'' if low is None else int(low)},{'' if high is None else int(high)}"


def search_url(query: dict[str, Any], page: int = 1) -> str:
    make, model = query["make"], query["model"]
    if not (_SLUG.match(make) and _SLUG.match(model)):
        raise KleinanzeigenError("invalid_filter", "Unexpected Kleinanzeigen make or model")
    segments = [make]
    if query.get("poster") in _POSTER.values():
        segments.append(f"anbieter:{query['poster']}")
    price = query.get("price")
    if price:
        segments.append("preis:" + price.replace(",", ":"))
    if page > 1:
        segments.append(f"seite:{page}")
    segments.append("sortierung:neuste")
    attributes = [
        f"autos.{key}:{quote(query[name], safe='')}"
        for key, name in (("ez_i", "year"), ("km_i", "mileage"))
        if query.get(name)
    ]
    attributes += [f"autos.marke_s:{make}", f"autos.model_s:{model}"]
    return f"{BASE_URL}/s-autos/{'/'.join(segments)}/{'+'.join([CATEGORY, *attributes])}"


def menu_options(page_html: str, attribute: str) -> list[TaxonomyOption]:
    """Menu items that select ``autos.<attribute>`` (``marke_s`` or ``model_s``)."""
    options: dict[str, TaxonomyOption] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            key, label, url = value.get("key"), value.get("localizedName"), value.get("url")
            if (
                isinstance(key, str)
                and isinstance(label, str)
                and isinstance(url, str)
                and _SLUG.match(key)
                and url.endswith(f"+autos.{attribute}:{key}")
            ):
                options.setdefault(key, TaxonomyOption(id=key, label=label))
            for child in value.values():
                visit(child)

    for _, props in island_props(page_html):
        visit(props)
    return list(options.values())


def result_ads(page_html: str) -> tuple[int, list[dict[str, Any]]]:
    """(total count, organic listings) of a search page."""
    tracker = next((props for name, props in island_props(page_html) if name == "ImpressionTracker"), None)
    if tracker is None:
        raise KleinanzeigenError("parse_error", "Kleinanzeigen search data not found (layout change)")
    ads = [
        ad["organicAdPreview"]
        for ad in tracker.get("resultAds") or []
        if isinstance(ad, dict) and isinstance(ad.get("organicAdPreview"), dict)
    ]
    return total_count(page_html), [ad for ad in ads if not ad.get("topAd")]


def total_count(page_html: str) -> int:
    """The "1 - 25 von 285 ..." summary above the results."""
    match = re.search(r'id="srp-breadcrumb-summary"[^>]*>[^<]*?von\s+([\d.]+)', page_html)
    return int(match.group(1).replace(".", "")) if match else 0


def parse_price(text: Any) -> tuple[Decimal | None, str | None]:
    """("25.200 € VB") -> (25200, "NEGOTIABLE"); no (or a placeholder) amount gives no price."""
    if not isinstance(text, str):
        return None, None
    match = _PRICE.match(text.strip())
    negotiable = text.strip().endswith("VB")
    if not match:
        return None, "NEGOTIABLE" if negotiable else None
    amount = Decimal(match.group(1).replace(".", ""))
    if amount < MIN_PRICE:
        return None, "NEGOTIABLE" if negotiable else None
    return amount, "NEGOTIABLE" if negotiable else "FIXED"


def parse_result(raw: Any) -> Listing | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), int):
        return None
    title, link = raw.get("title"), raw.get("seoLink")
    if not isinstance(title, str) or not isinstance(link, str) or not link.startswith("/s-anzeige/"):
        return None
    description = raw.get("description") if isinstance(raw.get("description"), str) else ""
    price, price_type = parse_price(raw.get("price"))

    specs: dict[str, float] = {}
    attributes: dict[str, str] = {"country": "DE"}
    for value in raw.get("attributes") or []:
        text = str(value).strip()
        if mileage := _MILEAGE.match(text):
            specs["mileage"] = int(mileage.group(1).replace(".", ""))
            attributes["mileage"] = str(int(specs["mileage"]))
        elif registration := _REGISTRATION.match(text):
            specs["year"] = int(registration.group(1))
            attributes["constructionYear"] = registration.group(1)
    battery = battery_kwh(title) or battery_kwh(description)
    if battery is not None:
        specs["battery"] = battery

    images = raw.get("imageList") or []
    image = images[0].get("xLargeUrl") if images and isinstance(images[0], dict) else None
    place = raw.get("parentLocationName") or raw.get("locationName")
    return Listing(
        item_id=f"k{raw['id']}",
        title=title.strip(),
        description=description,
        url=f"{BASE_URL}{link}",
        image_url=image if isinstance(image, str) else None,
        price=price,
        price_type=price_type,
        city=f"{place} (DE)" if place else None,
        distance_meters=None,
        attributes=attributes,
        seller_type=_SELLER_TYPES.get(str(raw.get("posterType"))),
        marketplace="kleinanzeigen",
        specs=specs,
    )


class KleinanzeigenClient:
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

    def page(self, url: str) -> str:
        return self._fetch(url)

    def search(self, query: dict[str, Any], *, max_pages: int = MAX_PAGES) -> SearchPage:
        listings: dict[str, Listing] = {}
        total = 0
        page = 1
        while page <= max_pages:
            if page > 1:
                self._sleep(self._page_delay)
            total, ads = result_ads(self._fetch(search_url(query, page)))
            found = [listing for raw in ads if (listing := parse_result(raw)) is not None]
            for listing in found:
                listings.setdefault(listing.item_id, listing)
            if not found or page * PAGE_SIZE >= total:
                break
            page += 1
        return SearchPage(
            total_count=total, listings=list(listings.values()), complete=len(listings) >= total
        )


class KleinanzeigenAdapter:
    """``PlatformAdapter`` for cars on Kleinanzeigen.de."""

    key = "kleinanzeigen"
    label = "Kleinanzeigen"

    def __init__(self, client: KleinanzeigenClient | None = None, cache: TtlCache | None = None) -> None:
        self.client = client or KleinanzeigenClient()
        self._cache = cache or TtlCache()

    def makes(self) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            makes = menu_options(self.client.page(f"{BASE_URL}/s-autos/{CATEGORY}"), "marke_s")
            if not makes:
                raise KleinanzeigenError("parse_error", "Kleinanzeigen returned no car makes")
            return makes

        return self._cache.get("makes", load)

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]:
        def load() -> list[TaxonomyOption]:
            if not _SLUG.match(make.id):
                return []
            page = self.client.page(f"{BASE_URL}/s-autos/{make.id}/{CATEGORY}+autos.marke_s:{make.id}")
            return [option for option in menu_options(page, "model_s") if option.id != "andere"]

        return self._cache.get(f"models:{make.id}", load)

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery:
        make = find_option(self.makes(), filters.make)
        if make is None:
            raise KleinanzeigenError("unsupported", f"{filters.make} is not available on Kleinanzeigen")
        model = find_option(self.models(make), filters.model)
        if model is None:
            raise KleinanzeigenError(
                "unsupported", f"{filters.make} {filters.model} is not available on Kleinanzeigen"
            )
        query: dict[str, Any] = {"make": make.id, "model": model.id}
        for key in ("year", "price", "mileage"):
            value = _range(filters.bounds(key))
            if value:
                query[key] = value
        if seller_type in _POSTER:
            query["poster"] = _POSTER[seller_type]
        active = filters.active_keys()
        return PlatformQuery(query=query, post_filters=[key for key in POST_FILTER_KEYS if key in active])

    def search(self, query: dict[str, Any], *, limit: int | None = None) -> SearchPage:
        return self.client.search(query, max_pages=1 if limit else MAX_PAGES)
