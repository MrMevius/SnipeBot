"""Types shared by the marketplace platform adapters.

Each platform (Marktplaats, AutoTrack, ...) implements ``PlatformAdapter``: it
lists the makes and models it knows, turns SnipeBot's own ``SearchFilters``
into a platform query and runs that query. Filters a platform cannot apply
itself are returned as ``post_filters``; SnipeBot then checks them against the
normalized ``Listing.specs`` (see ``snipebot.domain.search_filters``).
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Protocol, TypeVar

# Normalized filter keys. ``range`` (electric range, km) only has a minimum.
FILTER_KEYS = ("year", "price", "mileage", "range", "battery")

_MARKTPLAATS_ID = re.compile(r"^m(\d+)$")
_POWER_KW = re.compile(r"(\d{2,4})\s*kw\b", re.IGNORECASE)
_POWER_HP = re.compile(r"(\d{2,4})\s*(?:pk|ps|hp|cv|ch)\b", re.IGNORECASE)
HP_TO_KW = 0.7355
_NORMALIZE = re.compile(r"[^a-z0-9]+")

T = TypeVar("T")


class MarketplaceError(Exception):
    """Raised for invalid input and failed or unparsable platform responses.

    ``kind`` is one of ``invalid_url``, ``invalid_filter``, ``unsupported``,
    ``fetch_error``, ``blocked``, ``parse_error`` or ``gone``.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


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
    marketplace: str = "marktplaats"
    # Normalized numbers for filtering: year, mileage, range (km), battery (kWh),
    # power (kW).
    specs: dict[str, float] = field(default_factory=dict)
    license_plate: str | None = None

    @property
    def numeric_id(self) -> int | None:
        """Marktplaats ids (``m123``) increase over time; other platforms have none."""
        match = _MARKTPLAATS_ID.match(self.item_id)
        return int(match.group(1)) if match else None


@dataclass(slots=True)
class SearchPage:
    total_count: int
    listings: list[Listing]
    facets: list[dict[str, Any]] = field(default_factory=list)
    # True when ``listings`` holds the complete result set, so anything
    # missing from it has gone offline.
    complete: bool = False


@dataclass(slots=True)
class TaxonomyOption:
    id: str
    label: str


@dataclass(slots=True)
class PlatformQuery:
    query: dict[str, Any]
    post_filters: list[str]


@dataclass(slots=True)
class SearchFilters:
    make: str
    model: str
    year_min: int | None = None
    year_max: int | None = None
    price_min: int | None = None
    price_max: int | None = None
    mileage_min: int | None = None
    mileage_max: int | None = None
    range_min: int | None = None
    battery_min: int | None = None
    battery_max: int | None = None
    # Variant keys (see ``snipebot.domain.car_variants``); always checked by SnipeBot.
    variants: list[str] | None = None

    def bounds(self, key: str) -> tuple[int | None, int | None]:
        return getattr(self, f"{key}_min", None), getattr(self, f"{key}_max", None)

    def active_keys(self) -> list[str]:
        keys = [key for key in FILTER_KEYS if any(value is not None for value in self.bounds(key))]
        return [*keys, "variant"] if self.variants else keys

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchFilters:
        names = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in payload.items() if key in names})


@dataclass(frozen=True, slots=True)
class HomeLocation:
    """Where distances to listings are measured from (straight line)."""

    name: str
    latitude: float
    longitude: float
    postcode: str | None = None
    country: str = "NL"


def distance_meters(home: HomeLocation | None, latitude: Any, longitude: Any) -> int | None:
    """Great-circle distance from ``home``; None without usable coordinates."""
    if home is None or not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return None
    if latitude == 0 and longitude == 0:
        return None
    lat1, lon1, lat2, lon2 = map(
        math.radians, (home.latitude, home.longitude, float(latitude), float(longitude))
    )
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        (lon2 - lon1) / 2
    ) ** 2
    return round(2 * 6_371_000 * math.asin(math.sqrt(a)))


class PlatformAdapter(Protocol):
    key: str
    label: str

    def makes(self) -> list[TaxonomyOption]: ...

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]: ...

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery: ...

    def search(self, query: dict[str, Any], *, limit: int | None = None) -> SearchPage: ...


def power_kw(text: object) -> int | None:
    """kW from "208 kW (283 PK)", "320 pk" or "498pk (366kW)" (the kW value preferred)."""
    value = str(text or "")
    if match := _POWER_KW.search(value):
        return int(match.group(1))
    if match := _POWER_HP.search(value):
        return round(int(match.group(1)) * HP_TO_KW)
    return None


def normalize_label(value: str) -> str:
    return _NORMALIZE.sub("", value.lower())


def find_option(options: list[TaxonomyOption], label: str) -> TaxonomyOption | None:
    wanted = normalize_label(label)
    return next((option for option in options if normalize_label(option.label) == wanted), None)


class TtlCache:
    """Tiny in-process cache for taxonomy lookups (makes and models change rarely)."""

    def __init__(self, ttl_seconds: float = 12 * 3600, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, load: Callable[[], T]) -> T:
        now = self._clock()
        cached = self._values.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        value = load()
        self._values[key] = (now + self._ttl, value)
        return value
