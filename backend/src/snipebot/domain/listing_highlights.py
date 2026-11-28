"""The few car details worth showing in a listings table: drive and tow hitch.

Fuel and transmission say nothing for most searches (every Tesla is electric
and automatic), so the table shows only what tells cars apart. A detail is
shown only when a listing states it: in its title, its drive field, the
variant SnipeBot derived for it, or its options.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from snipebot.domain.car_variants import _AWD_TEXT, _RWD_TEXT

AWD = "AWD"
RWD = "RWD"
TOW_HITCH = "Tow hitch"

_VARIANT_DRIVE = {"sr": RWD, "lr_rwd": RWD, "lr_awd": AWD, "performance": AWD}
_TOW_HITCH = re.compile(
    r"trekhaak|tow\s*(?:bar|hitch)|trailer\s*hitch|anh(?:ä|ae|a)ngerkupplung|\bahk\b|attelage",
    re.IGNORECASE,
)


def drive(title: str, attributes: Mapping[str, str]) -> str | None:
    """AWD or RWD when the listing says so; the title wins over the fields."""
    for text in (title, attributes.get("driveTrain", "")):
        if _AWD_TEXT.search(text):
            return AWD
        if _RWD_TEXT.search(text):
            return RWD
    drives = {_VARIANT_DRIVE.get(key) for key in attributes.get("variant", "").split(",") if key}
    return drives.pop() if len(drives) == 1 else None


def has_tow_hitch(title: str, attributes: Mapping[str, str]) -> bool:
    return bool(_TOW_HITCH.search(title) or _TOW_HITCH.search(attributes.get("options", "")))


def car_highlights(listings: Iterable[tuple[str, Mapping[str, str]]]) -> list[str]:
    """Highlights of one car from all its listings (title, attributes)."""
    listings = list(listings)
    highlights = []
    drives = {drive(title, attributes) for title, attributes in listings} - {None}
    if len(drives) == 1:
        highlights.append(drives.pop())
    if any(has_tow_hitch(title, attributes) for title, attributes in listings):
        highlights.append(TOW_HITCH)
    return highlights
