from decimal import Decimal
from pathlib import Path

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

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            '<script type="application/ld+json">{"offers":{"price":"24.99"}}</script>',
            Decimal("24.99"),
        ),
        (
            "<script>{&quot;price&quot;:&quot;24.99&quot;}</script>",
            Decimal("24.99"),
        ),
        (
            "<script>{\\u0022price\\u0022\\u003a24\\u002e99}</script>",
            Decimal("24.99"),
        ),
        (
            '<meta property="product:price:amount" content="14.95" />',
            Decimal("14.95"),
        ),
        (
            '<meta content="1299,50" property="product:price:amount" />',
            Decimal("1299.50"),
        ),
        (
            "<span>€ 1.299,95</span>",
            Decimal("1299.95"),
        ),
    ],
)
def test_extract_price_supports_structured_and_formatted_sources(
    html: str,
    expected: Decimal,
) -> None:
    assert extract_price(html) == expected


def test_hema_adapter_parses_json_ld_price() -> None:
    adapter = HemaAdapter()
    html = """
    <html>
      <head>
        <title>Heren T-shirt slimfit</title>
        <script type="application/ld+json">
          {"@type":"Product","offers":{"@type":"Offer","price":"29.99","priceCurrency":"EUR"}}
        </script>
      </head>
      <body><div>Op voorraad</div></body>
    </html>
    """

    parsed = adapter.parse_html(
        "https://www.hema.nl/heren/herenkleding/shirts/example.html",
        html,
    )
    assert parsed.current_price == Decimal("29.99")
    assert parsed.currency == "EUR"
    assert parsed.availability == "in_stock"


def test_hema_adapter_parses_realistic_fixture_html() -> None:
    adapter = HemaAdapter()
    html = (FIXTURES_DIR / "hema_product_page_fixture.html").read_text(encoding="utf-8")

    parsed = adapter.parse_html(
        "https://www.hema.nl/heren/herenkleding/shirts/heren-t-shirts-slimfit-v-hals-extra-lang---2-stuks-zwart-34290650BLACK.html",
        html,
    )

    assert "HEMA" in parsed.title
    assert parsed.current_price == Decimal("24.99")
    assert parsed.currency == "EUR"
    assert parsed.availability == "in_stock"


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
