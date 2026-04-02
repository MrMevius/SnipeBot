from snipebot.adapters.sites.registry import detect_site_key


def test_detect_site_key_known_hosts() -> None:
    assert detect_site_key("https://www.hema.nl/product/1") == "hema"
    assert detect_site_key("https://amazon.nl/dp/abc") == "amazon_nl"
    assert detect_site_key("https://www.aliexpress.com/item/123.html") == "aliexpress"


def test_detect_site_key_unknown_host() -> None:
    assert detect_site_key("https://example.com/product") == "unknown"
