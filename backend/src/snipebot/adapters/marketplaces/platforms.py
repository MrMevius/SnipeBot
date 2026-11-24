"""Registry of the marketplace platforms SnipeBot can search."""

from __future__ import annotations

from snipebot.adapters.marketplaces.autotrack import AutoTrackAdapter
from snipebot.adapters.marketplaces.base import PlatformAdapter
from snipebot.adapters.marketplaces.marktplaats import MarktplaatsAdapter

# Display order in the UI and in merged make/model lists.
PLATFORM_LABELS = {"marktplaats": "Marktplaats", "autotrack": "AutoTrack"}

_adapters: dict[str, PlatformAdapter] | None = None


def get_adapters() -> dict[str, PlatformAdapter]:
    """Shared adapters, so their taxonomy caches survive between requests."""
    global _adapters
    if _adapters is None:
        _adapters = {"marktplaats": MarktplaatsAdapter(), "autotrack": AutoTrackAdapter()}
    return _adapters


def platform_label(key: str) -> str:
    return PLATFORM_LABELS.get(key, key)
