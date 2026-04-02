from decimal import Decimal

import pytest

from snipebot.adapters.sites.aliexpress import AliExpressAdapter
from snipebot.adapters.sites.amazon_nl import AmazonNlAdapter
from snipebot.adapters.sites.base import ParsedProductData, SiteAdapter
from snipebot.adapters.sites.hema import HemaAdapter
from snipebot.adapters.sites.parsing import (
    extract_price,
    extract_title,
    infer_availability,
)


def _sample_html(title: str, price: str) -> str:
    return f"""
    <html>
      <head><title>{title}</title></head>
      <body>
        <div>Op voorraad</div>
        <span>{price}</span>
      </body>
    </html>
    """


def test_site_adapters_parse_normalized_data() -> None:
    cases = [
        (HemaAdapter(), "https://www.hema.nl/product/1"),
        (AmazonNlAdapter(), "https://www.amazon.nl/dp/123"),
        (AliExpressAdapter(), "https://www.aliexpress.com/item/123.html"),
    ]

    for adapter, url in cases:
        parsed = adapter.parse_html(url, _sample_html("My Product", "€ 12,99"))
        assert isinstance(parsed, ParsedProductData)
        assert parsed.title == "My Product"
        assert parsed.current_price == Decimal("12.99")
        assert parsed.currency == "EUR"
        assert parsed.availability == "in_stock"
        assert parsed.parser_metadata


def test_parsing_edge_cases() -> None:
    assert extract_title("<title>  Fancy   Lamp  </title>") == "Fancy Lamp"
    assert extract_price("<span>EUR 12,50</span>") == Decimal("12.50")
    assert infer_availability("<p>Niet op voorraad</p>") == "out_of_stock"

    with pytest.raises(ValueError, match="Could not parse product title"):
        extract_title("<html><body>missing title</body></html>")

    with pytest.raises(ValueError, match="Could not parse product price"):
        extract_price("<span>Price unavailable</span>")


class _FallbackAdapter(SiteAdapter):
    site_key = "fake"
    supports_playwright_fallback = True

    def supports(self, url: str) -> bool:
        return True

    def parse_html(self, url: str, html: str) -> ParsedProductData:
        if "price-ok" not in html:
            raise ValueError("price marker missing")
        return ParsedProductData(
            title="fallback title",
            current_price=Decimal("10.00"),
            currency="EUR",
            availability="unknown",
            parser_metadata="from-fallback",
        )

    def _fetch_html(self, url: str) -> str:
        return "<html><title>x</title><div>no price</div></html>"

    def _fetch_html_playwright(self, url: str) -> str | None:
        return "<html><title>x</title><div>price-ok</div><span>€ 10,00</span></html>"


def test_adapter_fallback_runs_only_when_enabled() -> None:
    adapter = _FallbackAdapter()

    no_fallback = adapter.check("https://example.test", allow_playwright_fallback=False)
    assert no_fallback.ok is False
    assert no_fallback.status == "parse_error"
    assert no_fallback.used_fallback is False

    with_fallback = adapter.check(
        "https://example.test", allow_playwright_fallback=True
    )
    assert with_fallback.ok is True
    assert with_fallback.status == "ok"
    assert with_fallback.used_fallback is True
    assert with_fallback.data is not None
    assert with_fallback.data.current_price == Decimal("10.00")
