from snipebot.adapters.sites.base import ParsedProductData, SiteAdapter
from snipebot.adapters.sites.parsing import (
    extract_image_url,
    extract_price,
    extract_title,
    infer_availability,
)


class AmazonNlAdapter(SiteAdapter):
    site_key = "amazon_nl"
    supports_playwright_fallback = True

    def supports(self, url: str) -> bool:
        return self.host_from_url(url).endswith("amazon.nl")

    def parse_html(self, url: str, html: str) -> ParsedProductData:
        return ParsedProductData(
            title=extract_title(html),
            current_price=extract_price(html),
            currency="EUR",
            availability=infer_availability(html),
            image_url=extract_image_url(html, url),
            parser_metadata="amazon_nl:title+eur-regex",
        )
