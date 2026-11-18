import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from snipebot.adapters.sites.base import ParsedProductData, SiteAdapter

_JSON_LD = re.compile(
    r"""<script\b[^>]*\s+type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script\s*>""",
    re.IGNORECASE | re.DOTALL,
)
_AVAILABILITY = {
    "InStock": "in_stock",
    "OnlineOnly": "in_stock",
    "OutOfStock": "out_of_stock",
    "SoldOut": "out_of_stock",
    "Discontinued": "out_of_stock",
    "InStoreOnly": "out_of_stock",
}


class LidlNlAdapter(SiteAdapter):
    site_key = "lidl_nl"

    def supports(self, url: str) -> bool:
        return self.host_from_url(url) in {"lidl.nl", "www.lidl.nl"}

    def parse_html(self, url: str, html: str) -> ParsedProductData:
        for match in _JSON_LD.finditer(html):
            try:
                product = json.loads(match.group(1), parse_float=Decimal)
            except json.JSONDecodeError:
                continue
            if isinstance(product, dict) and product.get("@type") == "Product":
                break
        else:
            raise ValueError("Could not find Lidl product data")

        name = product.get("name")
        title = self.clean_text(name) if isinstance(name, str) else ""
        if not title:
            raise ValueError("Could not parse Lidl product title")

        offers = product.get("offers")
        offer = next(iter(offers), None) if isinstance(offers, list) else offers
        if not isinstance(offer, dict) or offer.get("priceCurrency") != "EUR":
            raise ValueError("Could not find a Lidl offer in EUR")
        try:
            price = Decimal(str(offer.get("price")))
        except InvalidOperation as exc:
            raise ValueError("Could not parse Lidl product price") from exc
        if not price.is_finite() or price < 0:
            raise ValueError("Invalid Lidl product price")

        availability = str(offer.get("availability")).rsplit("/", 1)[-1]
        images = product.get("image")
        image = next(iter(images), None) if isinstance(images, list) else images
        return ParsedProductData(
            title=title,
            current_price=price,
            currency="EUR",
            availability=_AVAILABILITY.get(availability, "unknown"),
            image_url=urljoin(url, image) if isinstance(image, str) and image else None,
            parser_metadata="lidl_nl:product-json-ld",
        )
