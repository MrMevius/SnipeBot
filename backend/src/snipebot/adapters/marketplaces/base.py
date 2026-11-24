"""Types shared by the marketplace platform adapters.

Each platform (Marktplaats, AutoTrack, ...) implements ``PlatformAdapter``: it
lists the makes and models it knows, turns SnipeBot's own ``SearchFilters``
into a platform query and runs that query. Filters a platform cannot apply
itself are returned as ``post_filters``; SnipeBot then checks them against the
normalized ``Listing.specs`` (see ``snipebot.domain.search_filters``).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Protocol, TypeVar

# Normalized filter keys. ``range`` (electric range, km) only has a minimum.
FILTER_KEYS = ("year", "price", "mileage", "range", "battery")

_MARKTPLAATS_ID = re.compile(r"^m(\d+)$")
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
    # Normalized numbers for filtering: year, mileage, range (km), battery (kWh).
    specs: dict[str, int] = field(default_factory=dict)
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

    def bounds(self, key: str) -> tuple[int | None, int | None]:
        return getattr(self, f"{key}_min", None), getattr(self, f"{key}_max", None)

    def active_keys(self) -> list[str]:
        return [key for key in FILTER_KEYS if any(value is not None for value in self.bounds(key))]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchFilters:
        names = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in payload.items() if key in names})


class PlatformAdapter(Protocol):
    key: str
    label: str

    def makes(self) -> list[TaxonomyOption]: ...

    def models(self, make: TaxonomyOption) -> list[TaxonomyOption]: ...

    def build_query(self, filters: SearchFilters, seller_type: str) -> PlatformQuery: ...

    def search(self, query: dict[str, Any], *, limit: int | None = None) -> SearchPage: ...


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
