"""Registry of the marketplace platforms SnipeBot can search."""

from __future__ import annotations

from snipebot.core.config import get_settings

from snipebot.adapters.marketplaces.base import HomeLocation, PlatformAdapter
from snipebot.adapters.marketplaces.marktplaats import TWEEDEHANDS, MarktplaatsAdapter
from snipebot.adapters.marketplaces.scout24 import AUTOSCOUT24, AUTOTRACK, Scout24Adapter
from snipebot.adapters.marketplaces.viabovag import ViaBovagAdapter

# Display order in the UI and in merged make/model lists.
PLATFORM_LABELS = {
    "marktplaats": "Marktplaats",
    "2dehands": "2dehands",
    "autoscout24": "AutoScout24",
    "viabovag": "ViaBOVAG",
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
        home = home_location()
        _adapters = {
            "marktplaats": MarktplaatsAdapter(home=home),
            "2dehands": MarktplaatsAdapter(site=TWEEDEHANDS, home=home),
            "autoscout24": Scout24Adapter(AUTOSCOUT24, home=home),
            "viabovag": ViaBovagAdapter(home=home),
            "autotrack": Scout24Adapter(AUTOTRACK, home=home),
        }
    return _adapters


def home_location() -> HomeLocation | None:
    """The configured home location (SNIPEBOT_HOME_*), if complete."""
    settings = get_settings()
    if settings.home_latitude is None or settings.home_longitude is None:
        return None
    return HomeLocation(
        name=settings.home_name or "home",
        latitude=settings.home_latitude,
        longitude=settings.home_longitude,
        postcode=settings.home_postcode,
        country=settings.home_country,
    )


def platform_label(key: str) -> str:
    return PLATFORM_LABELS.get(key, key)
