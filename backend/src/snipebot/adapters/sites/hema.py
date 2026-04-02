from snipebot.adapters.sites.base import ParsedProductData, SiteAdapter
from snipebot.adapters.sites.parsing import (
    extract_price,
    extract_title,
    infer_availability,
)


class HemaAdapter(SiteAdapter):
    site_key = "hema"
    supports_playwright_fallback = True

    def supports(self, url: str) -> bool:
        return self.host_from_url(url).endswith("hema.nl")

    def parse_html(self, url: str, html: str) -> ParsedProductData:
        return ParsedProductData(
            title=extract_title(html),
            current_price=extract_price(html),
            currency="EUR",
            availability=infer_availability(html),
            parser_metadata="hema:title+eur-regex",
        )
