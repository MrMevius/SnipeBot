import pytest

from snipebot.domain.services import normalize_product_url


def test_normalize_product_url_removes_tracking_bits() -> None:
    normalized = normalize_product_url(
        "https://WWW.AMAZON.NL:443/dp/B0123/?utm_source=mail&fbclid=123&a=1"
    )
    assert normalized == "https://amazon.nl/dp/B0123?a=1"


def test_normalize_product_url_rejects_invalid_scheme() -> None:
    with pytest.raises(ValueError):
        normalize_product_url("ftp://example.com/item")


def test_normalize_product_url_rejects_missing_host() -> None:
    with pytest.raises(ValueError):
        normalize_product_url("https:///missing-host")
