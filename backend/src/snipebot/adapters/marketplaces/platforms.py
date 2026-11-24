"""Registry of the marketplace platforms SnipeBot can search."""

from __future__ import annotations

from snipebot.adapters.marketplaces.base import PlatformAdapter
from snipebot.adapters.marketplaces.marktplaats import MarktplaatsAdapter
from snipebot.adapters.marketplaces.scout24 import AUTOSCOUT24, AUTOTRACK, Scout24Adapter

# Display order in the UI and in merged make/model lists.
PLATFORM_LABELS = {
    "marktplaats": "Marktplaats",
    "autoscout24": "AutoScout24",
    "autotrack": "AutoTrack",
}

# Platforms that show the same listings under the same ids: AutoScout24.nl
# includes every AutoTrack listing. A search or archive item moving from the
# second to the first keeps its listings, price history and photos.
SHARED_LISTING_IDS = {"autoscout24": "autotrack"}

_adapters: dict[str, PlatformAdapter] | None = None


def get_adapters() -> dict[str, PlatformAdapter]:
    """Shared adapters, so their taxonomy caches survive between requests."""
    global _adapters
    if _adapters is None:
        _adapters = {
            "marktplaats": MarktplaatsAdapter(),
            "autoscout24": Scout24Adapter(AUTOSCOUT24),
            "autotrack": Scout24Adapter(AUTOTRACK),
        }
    return _adapters


def platform_label(key: str) -> str:
    return PLATFORM_LABELS.get(key, key)
