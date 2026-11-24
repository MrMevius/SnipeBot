"""SnipeBot's own search filters: validation, description and post-filtering.

Platforms apply most filters themselves. Filters a platform cannot apply are
checked here against the listing's normalized specs. A listing whose value is
unknown is kept and marked, so nothing is hidden on missing data alone.
"""

from __future__ import annotations

from snipebot.adapters.marketplaces.base import FILTER_KEYS, Listing, SearchFilters

FILTER_LABELS = {
    "year": "Bouwjaar",
    "price": "Prijs",
    "mileage": "Kilometerstand",
    "range": "Actieradius",
    "battery": "Accucapaciteit",
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
    return SearchFilters.from_dict({**filters.to_dict(), "make": make, "model": model})


def describe_filters(filters: SearchFilters, seller_type: str = "all") -> list[str]:
    """Human-readable (Dutch) summary of the filters."""
    lines = [f"Auto: {filters.make} {filters.model}"]
    for key in filters.active_keys():
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
        low, high = filters.bounds(key)
        if low is None and high is None:
            continue
        value = listing.price if key == "price" else listing.specs.get(key)
        if value is None:
            unknown.append(key)
        elif (low is not None and value < low) or (high is not None and value > high):
            return False, []
    return True, unknown


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
