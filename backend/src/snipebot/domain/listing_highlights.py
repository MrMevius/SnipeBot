"""The few car details worth showing in a listings table: drive and tow hitch.

Fuel and transmission say nothing for most searches (every Tesla is electric
and automatic), so the table shows only what tells cars apart. A detail is
shown only when a listing states it: in its title, its drive field, the
variant SnipeBot derived for it, its options or its archived description.

Descriptions also mention a tow hitch the car does not have, so a mention
there counts only when its line does not deny it ("geen trekhaak",
"Anhängerkupplung: --") or make it conditional ("bij montage van een
trekhaak", "trekhaak optioneel").
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
    r"trekhaak|tow\s*(?:bar|hitch)|trailer\s*hitch|anh(?:ä|ae|a)ngerkupplung|\bahk\b|attelage|attache[\s-]*remorque",
    re.IGNORECASE,
)
# "geen trekhaak", "ohne AHK", "no tow bar", "sans attelage", "zonder (afneembare) trekhaak".
_DENIED_BEFORE = re.compile(
    r"\b(?:geen|zonder|niet|kein\w*|ohne|no|without|sans|pas d[e'’]?)\s+(?:[\w-]+\s+){0,2}$",
    re.IGNORECASE,
)
# A field without a value: "Anhängerkupplung: --", "Trekhaak: nee".
_EMPTY_VALUE = re.compile(
    r"^\s*[:=]\s*(?:$|-+\s*$|(?:nee|neen|nein|no|non|none|geen|keine?|n\.?v\.?t\.?|nicht vorhanden)\b)",
    re.IGNORECASE,
)
# Fitting it is possible, optional or costs extra; the car does not have it yet.
_CONDITIONAL = re.compile(
    r"\bmontage\b|mogelijk|möglich|optioneel|optional|nachrüst\w*|leverbaar|meerprijs|aufpreis"
    r"|kan\s+(?:\w+\s+){0,3}(?:worden|gemonteerd|geplaatst)|can\s+be\s+fitted",
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


def description_has_tow_hitch(description: str | None) -> bool:
    """A description line states the car has a tow hitch."""
    for line in (description or "").splitlines():
        if _CONDITIONAL.search(line):
            continue
        for match in _TOW_HITCH.finditer(line):
            if _DENIED_BEFORE.search(line[: match.start()]) or _EMPTY_VALUE.match(line[match.end() :]):
                continue
            return True
    return False


def has_tow_hitch(title: str, attributes: Mapping[str, str], description: str | None = None) -> bool:
    return bool(
        _TOW_HITCH.search(title)
        or _TOW_HITCH.search(attributes.get("options", ""))
        or description_has_tow_hitch(description)
    )


def car_highlights(listings: Iterable[tuple[str, Mapping[str, str], str | None]]) -> list[str]:
    """Highlights of one car from all its listings (title, attributes, description)."""
    listings = list(listings)
    highlights = []
    drives = {drive(title, attributes) for title, attributes, _ in listings} - {None}
    if len(drives) == 1:
        highlights.append(drives.pop())
    if any(has_tow_hitch(*listing) for listing in listings):
        highlights.append(TOW_HITCH)
    return highlights
