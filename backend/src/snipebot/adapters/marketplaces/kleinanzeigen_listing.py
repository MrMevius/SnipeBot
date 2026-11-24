"""Kleinanzeigen listing pages (``/s-anzeige/<slug>/<id>-216-<place>``): full details for the archive.

Listing pages are server-rendered HTML with stable ``viewad-*`` ids: title,
price, place, the vehicle details list, the equipment tags, the description
and the seller box. Photos are the gallery's JSON-LD image objects (other
ads further down the page have JSON-LD images too); the seller
type and ad id also appear in the page's analytics settings. A removed ad
redirects to a category page, which ``curl`` reports as ``gone``.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlsplit

from snipebot.adapters.marketplaces.kleinanzeigen import (
    BASE_URL,
    IMAGE_HOSTS,
    KLEINANZEIGEN_HOSTS,
    Fetcher,
    KleinanzeigenError,
    curl,
    http_fetch,
    parse_price,
)
from snipebot.adapters.marketplaces.marktplaats_listing import (
    MAX_IMAGE_BYTES,
    ListingDetail,
    ListingImage,
    sanitize_description,
)

_LISTING_PATH = re.compile(r"^/s-anzeige/[^/]+/(\d+)-\d+-\d+$")
_TAG = re.compile(r"<[^>]+>")
_JSON_LD = re.compile(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', re.DOTALL)
_DETAIL = re.compile(
    r'<li class="addetailslist--detail">(.*?)<span class="addetailslist--detail--value"[^>]*>(.*?)</span>',
    re.DOTALL,
)
_CHECKTAG = re.compile(r'<li class="checktag">(.*?)</li>', re.DOTALL)
_IMAGE_KEY = re.compile(r"/prod-ads/images/([0-9a-f]{2}/[0-9a-f-]{36})")
_SELLER_TYPES = {"Private": "CONSUMER", "Trade": "TRADER", "Commercial": "TRADER"}


def validate_listing_url(url: str) -> tuple[str, str]:
    """(canonical URL, item id) of a kleinanzeigen.de listing URL."""
    parts = urlsplit(url.strip())
    match = _LISTING_PATH.match(parts.path)
    if parts.scheme not in {"http", "https"} or parts.hostname not in KLEINANZEIGEN_HOSTS or not match:
        raise KleinanzeigenError("invalid_url", "Not a kleinanzeigen.de listing URL")
    return f"{BASE_URL}{parts.path}", f"k{match.group(1)}"


def fetch_listing(url: str, *, fetch: Fetcher | None = None) -> ListingDetail:
    page_url, _ = validate_listing_url(url)
    return parse_listing_page((fetch or http_fetch)(page_url), url=page_url)


def parse_listing_page(page_html: str, *, url: str) -> ListingDetail:
    _, item_id = validate_listing_url(url)
    title = _text(_element(page_html, "h1", "viewad-title"))
    if not title:
        raise KleinanzeigenError("parse_error", "Kleinanzeigen listing data not found (layout change)")
    price, price_type = parse_price(_text(_element(page_html, "h2", "viewad-price")))
    postcode, city = _locality(_text(_element(page_html, "span", "viewad-locality")))

    details = [
        {"key": "", "label": _text(label), "value": _text(value)}
        for label, value in _DETAIL.findall(_section(page_html, "viewad-details"))
        if _text(label) and _text(value)
    ]
    groups: list[dict[str, Any]] = []
    if details:
        groups.append({"label": "Fahrzeugdaten", "items": details})
    equipment = [_text(tag) for tag in _CHECKTAG.findall(_section(page_html, "viewad-configuration"))]
    if equipment:
        groups.append(
            {"label": "Ausstattung", "items": [{"key": "options", "label": "Ausstattung", "value": ", ".join(equipment)}]}
        )
    category = [item["value"] for item in details if item["label"] in {"Marke", "Modell"}]
    description_html, description_text = sanitize_description(
        _element(page_html, "p", "viewad-description-text") or ""
    )
    return ListingDetail(
        item_id=item_id,
        title=title,
        url=url,
        price=price,
        price_type=price_type,
        category=category,
        description_html=description_html,
        description_text=description_text,
        attribute_groups=groups,
        images=_images(page_html),
        seller=_seller(page_html, city),
        stats={},
        highlights=[],
        city=f"{city} (DE)" if city else None,
        postcode=postcode,
        is_reserved=False,
    )


def image_fetch(url: str) -> bytes:
    """Download a listing photo; only Kleinanzeigen's image host is allowed."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        raise KleinanzeigenError("invalid_url", "Unexpected image host")
    return curl(url, accept="image/*", max_bytes=MAX_IMAGE_BYTES)


def _element(page_html: str, tag: str, element_id: str) -> str | None:
    match = re.search(rf'<{tag}\b[^>]*\bid="{element_id}"[^>]*>(.*?)</{tag}>', page_html, re.DOTALL)
    return match.group(1) if match else None


def _section(page_html: str, element_id: str) -> str:
    """Markup from the element with ``element_id`` up to the next ``splitlinebox``."""
    start = page_html.find(f'id="{element_id}"')
    if start < 0:
        return ""
    end = page_html.find('class="splitlinebox', start + 1)
    return page_html[start : end if end > 0 else len(page_html)]


def _text(fragment: str | None) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment or "")).split())


def _locality(text: str) -> tuple[str | None, str | None]:
    """"66127 Saarbrücken-West - Klarenthal" -> ("66127", "Klarenthal")."""
    match = re.match(r"^(\d{5})\s+(.*)$", text)
    postcode, place = (match.group(1), match.group(2)) if match else (None, text)
    city = place.rsplit(" - ", 1)[-1].strip() if place else ""
    return postcode, city or None


def _images(page_html: str) -> list[ListingImage]:
    """The gallery's photos; the page also holds JSON-LD images of other ads."""
    start = page_html.find('class="galleryimage-element')
    end = page_html.find('id="viewad-lightbox"', start)
    if start < 0:
        return []
    images: dict[str, ListingImage] = {}
    for block in _JSON_LD.findall(page_html[start : end if end > 0 else len(page_html)]):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        url = data.get("contentUrl") if isinstance(data, dict) and data.get("@type") == "ImageObject" else None
        if not isinstance(url, str) or urlsplit(url).hostname not in IMAGE_HOSTS:
            continue
        key = _IMAGE_KEY.search(url)
        if key and key.group(1) not in images:
            images[key.group(1)] = ListingImage(key=key.group(1), url=url)
    return list(images.values())


def _seller(page_html: str, city: str | None) -> dict[str, Any]:
    seller: dict[str, Any] = {}
    box = _section(page_html, "viewad-contact")
    name = re.search(r'class="[^"]*userprofile-vip"[^>]*>\s*<a [^>]*>(.*?)</a>', box, re.DOTALL)
    if name and _text(name.group(1)):
        seller["name"] = _text(name.group(1))
    kind = re.search(r'"ad_seller_type":"([^"]*)"', page_html)
    if kind and kind.group(1) in _SELLER_TYPES:
        seller["sellerType"] = _SELLER_TYPES[kind.group(1)]
    since = re.search(r"Aktiv seit ([\d.]+)", box)
    if since:
        seller["activeSince"] = since.group(1)
    if city:
        seller["city"] = city
    return seller
