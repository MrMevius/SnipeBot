"""SnipeBot's own search filters: validation, description and post-filtering.

Platforms apply most filters themselves. Filters a platform cannot apply are
checked here against the listing's normalized specs. A listing whose value is
unknown is kept and marked, so nothing is hidden on missing data alone.
"""

from __future__ import annotations

from snipebot.adapters.marketplaces.base import FILTER_KEYS, Listing, SearchFilters
from snipebot.domain import car_variants

FILTER_LABELS = {
    "year": "Bouwjaar",
    "price": "Prijs",
    "mileage": "Kilometerstand",
    "range": "Actieradius",
    "battery": "Accucapaciteit",
    "variant": "Uitvoering",
}
_SELLER_LABELS = {"private": "Particulier", "business": "Bedrijf"}
_MAX_VALUE = 100_000_000


def validate_filters(filters: SearchFilters) -> SearchFilters:
    make = " ".join(filters.make.split())
    model = " ".join(filters.model.split())
    if not make or not model:
        raise ValueError("Choose a make and a model")
    for key in FILTER_KEYS:
        low, high = filters.bounds(key)
        for value in (low, high):
            if value is not None and not 0 <= value <= _MAX_VALUE:
                raise ValueError(f"{FILTER_LABELS[key]}: enter a value between 0 and {_MAX_VALUE}")
        if low is not None and high is not None and low > high:
            raise ValueError(f"{FILTER_LABELS[key]}: the minimum is above the maximum")
    variants = _validate_variants(filters, make, model)
    return SearchFilters.from_dict(
        {**filters.to_dict(), "make": make, "model": model, "variants": variants}
    )


def _validate_variants(filters: SearchFilters, make: str, model: str) -> list[str] | None:
    if not filters.variants:
        return None
    if not car_variants.supports_variants(make, model):
        raise ValueError(f"Uitvoering: not available for {make} {model}")
    if filters.year_min is None or filters.year_min < car_variants.MIN_YEAR:
        raise ValueError(f"Uitvoering: set the year from {car_variants.MIN_YEAR} or later")
    unknown = set(filters.variants) - car_variants.ALL_VARIANTS
    if unknown:
        raise ValueError(f"Uitvoering: unknown variant {', '.join(sorted(unknown))}")
    return [key for key in car_variants.VARIANT_LABELS if key in filters.variants]


def describe_filters(filters: SearchFilters, seller_type: str = "all") -> list[str]:
    """Human-readable (Dutch) summary of the filters."""
    lines = [f"Auto: {filters.make} {filters.model}"]
    for key in filters.active_keys():
        if key == "variant":
            lines.append(f"{FILTER_LABELS[key]}: {car_variants.describe(filters.variants or [])}")
            continue
        low, high = filters.bounds(key)
        low_text, high_text = _format(key, low), _format(key, high)
        if low_text and high_text:
            lines.append(f"{FILTER_LABELS[key]}: {low_text} t/m {high_text}")
        elif low_text:
            lines.append(f"{FILTER_LABELS[key]}: vanaf {low_text}")
        elif high_text:
            lines.append(f"{FILTER_LABELS[key]}: t/m {high_text}")
    if seller_type in _SELLER_LABELS:
        lines.append(f"Verkoper: {_SELLER_LABELS[seller_type]}")
    return lines


def check_listing(
    filters: SearchFilters, listing: Listing, keys: list[str]
) -> tuple[bool, list[str]]:
    """Return (matches, keys whose value is unknown) for the given filter keys."""
    unknown: list[str] = []
    for key in keys:
        if key == "variant":
            if not filters.variants:
                continue
            possible = listing_variant_set(listing)
            if possible is None or not possible <= set(filters.variants):
                if possible is not None and not possible & set(filters.variants):
                    return False, []
                unknown.append(key)
            continue
        low, high = filters.bounds(key)
        if low is None and high is None:
            continue
        value = listing.price if key == "price" else listing.specs.get(key)
        if value is None:
            unknown.append(key)
        elif (low is not None and value < low) or (high is not None and value > high):
            return False, []
    return True, unknown


def listing_variant_set(listing: Listing) -> set[str] | None:
    """The variants a listing can be, as resolved into ``attributes["variant"]``."""
    value = (listing.attributes or {}).get("variant")
    return set(value.split(",")) if value else None


def _format(key: str, value: int | None) -> str | None:
    if value is None:
        return None
    number = f"{value:,}".replace(",", ".")
    if key == "price":
        return f"€ {number}"
    if key in {"mileage", "range"}:
        return f"{number} km"
    if key == "battery":
        return f"{number} kWh"
    return str(value)
