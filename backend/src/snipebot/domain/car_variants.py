"""Which variant of a car a listing offers, for the "Uitvoering" filter.

Only the Tesla Model 3 from 2024 on (the "Highland" generation) is known. Its
variants differ in power, battery and range, and the drive (RWD/AWD) splits
Long Range in two:

=================  =================  ========  ===========
Variant            Power              Battery   WLTP range
=================  =================  ========  ===========
sr                 208 kW / 283 pk    ~60 kWh   513-572 km
lr_rwd (2025 on)   235 kW / 320 pk    78 kWh    ~700 km
lr_awd             366 kW / 498 pk    78-82     629-660 km
performance        460 kW / 626 pk    78-82     528-571 km
=================  =================  ========  ===========

Each signal narrows the set of possible variants. Sellers fill in fields
wrongly now and then (a "78 kWh Long Range" with 208 kW), so signals are
applied in order of reliability (title/version text, battery, power, drive,
range) and a signal that contradicts the earlier ones is ignored. The result
is the set of variants the listing can be; ``None`` when nothing narrows it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from snipebot.adapters.marketplaces.base import normalize_label
from snipebot.adapters.marketplaces.base import power_kw as parse_power

VARIANT_LABELS = {
    "sr": "Standard Range",
    "lr_rwd": "Long Range RWD",
    "lr_awd": "Long Range AWD",
    "performance": "Performance",
}
ALL_VARIANTS = frozenset(VARIANT_LABELS)
# The table above only holds from this model year on.
MIN_YEAR = 2024

_RWD = r"rwd|rear[- ]wheel|achterwiel\w*|heckantrieb|hinter\w*antrieb|hinterrad\w*|propulsion|single motor"
_AWD = r"awd|all[- ]wheel|dual[- ]?motor|4x4|4wd|allrad\w*|vierwiel\w*|int[ée]grale|transmission int"
_LONG_RANGE = re.compile(
    r"long\s*range|longrange|\blr\b|grande autonomie|max(?:imale)?\.?\s*reichweite|langstrecke\w*",
    re.IGNORECASE,
)
_STANDARD = re.compile(r"\bstandar[dt]\b|\bsr\+?(?=\W|$)", re.IGNORECASE)
_PERFORMANCE = re.compile(r"\bperformance\b", re.IGNORECASE)
# "Premium" says nothing: dealers use it for every variant ("Premium LFP RWD 60 kWh").
_RWD_TEXT = re.compile(rf"\b(?:{_RWD})(?![a-z])", re.IGNORECASE)
_AWD_TEXT = re.compile(rf"\b(?:{_AWD})(?![a-z])", re.IGNORECASE)
_BATTERY = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*kwh?(?!\s*/)", re.IGNORECASE)
_NUMBER = re.compile(r"\d{2,4}")

_VERSION_LABEL = re.compile(r"uitvoering|version|variante|ausführung", re.IGNORECASE)
_POWER_LABEL = re.compile(r"vermogen|leistung|power|puissance", re.IGNORECASE)
_BATTERY_LABEL = re.compile(r"accu|batter", re.IGNORECASE)
_RANGE_LABEL = re.compile(r"actieradius|reichweite|range|autonomie", re.IGNORECASE)
_DRIVE_LABEL = re.compile(r"aandrijving|antrieb|drive|transmission", re.IGNORECASE)
_SKIP_LABEL = re.compile(r"verbranding|laad|lade|charg|conditie|zustand|type|bruikbaar|soh", re.IGNORECASE)


def supports_variants(make: str, model: str) -> bool:
    return normalize_label(make) == "tesla" and normalize_label(model) in {"model3", "3"}


def from_text(text: str) -> frozenset[str] | None:
    """Variants named in a title or version text ("Long Range AWD", "SR+")."""
    if _PERFORMANCE.search(text):
        return frozenset({"performance"})
    if _LONG_RANGE.search(text):
        if _RWD_TEXT.search(text):
            return frozenset({"lr_rwd"})
        if _AWD_TEXT.search(text):
            return frozenset({"lr_awd"})
        return frozenset({"lr_rwd", "lr_awd"})
    if _STANDARD.search(text):
        return frozenset({"sr"})
    return drive_variants(text)


def drive_variants(text: str) -> frozenset[str] | None:
    """Before 2025 "RWD" meant Standard Range; since then Long Range RWD exists too."""
    if _AWD_TEXT.search(text):
        return frozenset({"lr_awd", "performance"})
    if _RWD_TEXT.search(text):
        return frozenset({"sr", "lr_rwd"})
    return None


def battery_variants(kwh: float | None) -> frozenset[str] | None:
    if kwh is None:
        return None
    if 55 <= kwh <= 64:
        return frozenset({"sr"})
    if 74 <= kwh <= 86:
        return frozenset({"lr_rwd", "lr_awd", "performance"})
    return None


def power_variants(kw: float | None) -> frozenset[str] | None:
    if kw is None:
        return None
    for low, high, variant in ((195, 215, "sr"), (225, 245, "lr_rwd"), (355, 375, "lr_awd"), (440, 475, "performance")):
        if low <= kw <= high:
            return frozenset({variant})
    return None


def range_variants(km: float | None) -> frozenset[str] | None:
    if km is None:
        return None
    if 500 <= km <= 580:
        return frozenset({"sr", "performance"})
    if 620 <= km <= 675:
        return frozenset({"lr_awd"})
    if 690 <= km <= 720:
        return frozenset({"lr_rwd"})
    return None


def combine(signals: Iterable[frozenset[str] | None]) -> frozenset[str] | None:
    """Narrow down in order; a signal that leaves nothing contradicts and is ignored."""
    possible = ALL_VARIANTS
    for signal in signals:
        if signal and possible & signal:
            possible = possible & signal
    return None if possible == ALL_VARIANTS else possible


def classify(
    title: str,
    *,
    version: str = "",
    power_kw: float | None = None,
    battery_kwh: float | None = None,
    range_km: float | None = None,
    drive: str = "",
) -> frozenset[str] | None:
    text = f"{title} {version}"
    battery = battery_kwh if battery_kwh is not None else _battery_from_text(text)
    if power_kw is None:
        power_kw = parse_power(text)
    return combine(
        (
            from_text(text),
            battery_variants(battery),
            power_variants(power_kw),
            drive_variants(drive),
            range_variants(range_km),
        )
    )


def listing_variants(listing: Any) -> frozenset[str] | None:
    """Variants from a search result (``Listing``)."""
    attributes = listing.attributes or {}
    return classify(
        listing.title,
        power_kw=listing.specs.get("power"),
        battery_kwh=listing.specs.get("battery"),
        range_km=listing.specs.get("range"),
        drive=str(attributes.get("driveTrain") or ""),
    )


def detail_variants(title: str, attribute_groups: list[dict[str, Any]]) -> frozenset[str] | None:
    """Variants from a listing page's labelled attributes (the archive's ``ListingDetail``)."""
    version, drive = [], []
    power = battery = range_km = None
    for group in attribute_groups:
        for item in group.get("items") or []:
            label, value = str(item.get("label") or ""), str(item.get("value") or "")
            if not value or _SKIP_LABEL.search(label):
                continue
            if _VERSION_LABEL.search(label):
                version.append(value)
            elif _POWER_LABEL.search(label) and power is None:
                power = parse_power(value)
            elif _BATTERY_LABEL.search(label) and battery is None:
                battery = _battery_from_text(value if "kw" in value.lower() else f"{value} kWh")
            elif _RANGE_LABEL.search(label) and range_km is None:
                number = _NUMBER.search(value.replace(".", ""))
                range_km = int(number.group(0)) if number else None
            elif _DRIVE_LABEL.search(label):
                drive.append(value)
    return classify(
        title,
        version=" ".join(version),
        power_kw=power,
        battery_kwh=battery,
        range_km=range_km,
        drive=" ".join(drive),
    )


def _battery_from_text(text: str) -> float | None:
    match = _BATTERY.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 10 <= value <= 250 else None


def describe(variants: Iterable[str]) -> str:
    return ", ".join(VARIANT_LABELS[key] for key in VARIANT_LABELS if key in set(variants))
