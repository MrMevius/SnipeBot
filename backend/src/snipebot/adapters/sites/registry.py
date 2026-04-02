from urllib.parse import urlparse

from snipebot.adapters.sites.aliexpress import AliExpressAdapter
from snipebot.adapters.sites.amazon_nl import AmazonNlAdapter
from snipebot.adapters.sites.base import SiteAdapter
from snipebot.adapters.sites.hema import HemaAdapter

_ADAPTERS: dict[str, SiteAdapter] = {
    "hema": HemaAdapter(),
    "amazon_nl": AmazonNlAdapter(),
    "aliexpress": AliExpressAdapter(),
}


def detect_site_key(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()

    if host.endswith("hema.nl"):
        return "hema"
    if host.endswith("amazon.nl"):
        return "amazon_nl"
    if host.endswith("aliexpress.com"):
        return "aliexpress"

    return "unknown"


def get_adapter(site_key: str) -> SiteAdapter | None:
    return _ADAPTERS.get(site_key)
