"""Marktplaats and 2dehands listing pages (``/v/...``): full details for the local archive.

A listing page embeds most of its data as ``window.__CONFIG__`` JSON: title,
price, gallery, seller and statistics, and for cars the labelled attributes.
The description and the attributes of non-car listings are only rendered as
HTML, so those are read from the markup. Descriptions are reduced to a small
allowlist of formatting tags before they are stored or shown.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from snipebot.adapters.marketplaces.marktplaats import (
    MARKTPLAATS,
    USER_AGENT,
    Fetcher,
    MarktplaatsError,
    MarktplaatsSite,
    _city_label,
    _http_fetch,
)

IMAGE_HOSTS = {"images.marktplaats.com", "images.2dehands.com"}
# "original" drops the resize rule: the uploaded file, byte-identical to the largest size.
DEFAULT_IMAGE_SIZE = "original"
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_CONFIG_MARKER = re.compile(r"window\.__CONFIG__\s*=\s*")
_ITEM_PATH = re.compile(r"^/v/.+/m\d+")
_ALLOWED_TAGS = {"br", "p", "strong", "b", "em", "i", "u", "ul", "ol", "li"}
_BLOCK_TAGS = {"br", "p", "li", "ul", "ol", "div"}
_SKIPPED_CONTENT_TAGS = {"script", "style", "template", "iframe", "noscript"}
_VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
# The "Main" group repeats the most important attributes of the other groups.
_CAR_GROUP_LABELS = {
    "Basics": "Basis",
    "Technical": "Techniek",
    "Eco": "Milieu",
    "History": "Historie",
    "Options": "Opties",
}
_SELLER_FIELDS = (
    "id",
    "name",
    "sellerType",
    "activeSinceDiff",
    "activeYears",
    "phoneNumber",
    "sellerWebsiteDisplayUrl",
)
_SELLER_URL_FIELDS = ("sellerProfileUrl", "allAdsUrl", "sellerWebsiteUrl")

ImageFetcher = Callable[[str], bytes]


@dataclass(slots=True)
class ListingImage:
    key: str
    url: str


@dataclass(slots=True)
class ListingDetail:
    item_id: str
    title: str
    url: str
    price: Decimal | None
    price_type: str | None
    category: list[str]
    description_html: str
    description_text: str
    attribute_groups: list[dict[str, Any]]
    images: list[ListingImage]
    seller: dict[str, Any]
    stats: dict[str, Any]
    highlights: list[str]
    city: str | None
    postcode: str | None
    is_reserved: bool
    ad_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        """Versioned content. Statistics change constantly and are left out."""
        return {
            "title": self.title,
            "price": str(self.price) if self.price is not None else None,
            "price_type": self.price_type,
            "category": self.category,
            "description_html": self.description_html,
            "description_text": self.description_text,
            "attribute_groups": self.attribute_groups,
            "seller": self.seller,
            "highlights": self.highlights,
            "city": self.city,
            "is_reserved": self.is_reserved,
            "images": [asdict(image) for image in self.images],
        }

    def content_hash(self) -> str:
        snapshot = self.snapshot()
        # Image URLs may carry changing query details; the key identifies a photo.
        snapshot["images"] = [image.key for image in self.images]
        payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_listing_url(url: str, site: MarktplaatsSite = MARKTPLAATS) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or parts.hostname not in site.hosts:
        raise MarktplaatsError("invalid_url", f"Not a {site.label} listing URL")
    if not _ITEM_PATH.match(parts.path):
        raise MarktplaatsError("invalid_url", f"Not a {site.label} listing URL")
    return f"{site.base_url}{parts.path}"


def fetch_listing(
    url: str,
    *,
    fetch: Fetcher | None = None,
    image_size: str = DEFAULT_IMAGE_SIZE,
    site: MarktplaatsSite = MARKTPLAATS,
) -> ListingDetail:
    page_url = validate_listing_url(url, site)
    if fetch is not None:
        page_html = fetch(page_url, "text/html")
    else:
        page_html = _http_fetch(page_url, "text/html", site.label)
    return parse_listing_page(page_html, url=page_url, image_size=image_size, site=site)


def parse_listing_page(
    page_html: str,
    *,
    url: str,
    image_size: str = DEFAULT_IMAGE_SIZE,
    site: MarktplaatsSite = MARKTPLAATS,
) -> ListingDetail:
    listing = _config_listing(page_html)
    item_id = listing.get("itemId")
    title = listing.get("title")
    if not isinstance(item_id, str) or not isinstance(title, str):
        raise MarktplaatsError("parse_error", "Listing page has no item id or title")

    markup = _ListingMarkup()
    markup.feed(page_html)
    markup.close()

    price_info = listing.get("priceInfo") or {}
    price_cents = price_info.get("priceCents")
    seller_raw = listing.get("seller") or {}
    location = seller_raw.get("location") or {}
    category = listing.get("category") or {}

    attribute_groups = _car_attribute_groups(listing.get("carAttributes"))
    if not attribute_groups and markup.attributes:
        attribute_groups = [{"label": "Kenmerken", "items": markup.attributes}]

    return ListingDetail(
        item_id=item_id,
        title=title.strip(),
        url=url,
        price=Decimal(int(price_cents)) / 100
        if isinstance(price_cents, int) and price_cents > 0
        else None,
        price_type=price_info.get("priceType"),
        category=[
            str(name)
            for name in (category.get("parentName"), category.get("name"))
            if name
        ],
        description_html=markup.description_html(),
        description_text=markup.description_text(),
        attribute_groups=attribute_groups,
        images=_gallery_images(listing.get("gallery") or {}, image_size),
        seller=_seller(seller_raw, site.base_url),
        stats={
            key: value
            for key, value in (listing.get("stats") or {}).items()
            if key in {"viewCount", "favoritedCount", "since"}
        },
        highlights=[
            str(item["key"])
            for item in listing.get("highlights") or []
            if isinstance(item, dict) and item.get("key")
        ],
        city=_city_label(location.get("cityName"), site),
        postcode=location.get("postcode") or None,
        is_reserved=bool(listing.get("isReserved")),
        ad_type=listing.get("adType"),
    )


def image_fetch(url: str) -> bytes:
    """Download a listing photo; only Marktplaats' image host is allowed."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        raise MarktplaatsError("invalid_url", "Unexpected image host")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except HTTPError as exc:
        kind = "blocked" if exc.code in {403, 429} else "fetch_error"
        raise MarktplaatsError(kind, f"Image request returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise MarktplaatsError("fetch_error", f"Image request failed: {exc}") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise MarktplaatsError("fetch_error", "Image is too large")
    return data


def sanitize_description(fragment: str) -> tuple[str, str]:
    """(allowlisted HTML, plain text) of a description given as an HTML fragment."""
    markup = _ListingMarkup()
    markup.feed(f'<div data-collapsable="description">{fragment}</div>')
    markup.close()
    return markup.description_html(), markup.description_text()


def _config_listing(page_html: str) -> dict[str, Any]:
    match = _CONFIG_MARKER.search(page_html)
    if match is None:
        raise MarktplaatsError("parse_error", "Listing page has no embedded data")
    try:
        config, _ = json.JSONDecoder().raw_decode(page_html, match.end())
    except json.JSONDecodeError as exc:
        raise MarktplaatsError("parse_error", "Listing page data is not valid JSON") from exc
    listing = config.get("listing") if isinstance(config, dict) else None
    if not isinstance(listing, dict):
        raise MarktplaatsError("parse_error", "Listing page has no listing data")
    return listing


def _car_attribute_groups(car_attributes: Any) -> list[dict[str, Any]]:
    if not isinstance(car_attributes, dict):
        return []
    groups: list[dict[str, Any]] = []
    for group in car_attributes.get("groupedWithIcons") or []:
        if not isinstance(group, dict) or group.get("key") == "Main":
            continue
        items: list[dict[str, str]] = []
        for attribute in group.get("attributes") or []:
            if not isinstance(attribute, dict) or not attribute.get("label"):
                continue
            if isinstance(attribute.get("values"), list):
                value = ", ".join(str(item) for item in attribute["values"])
            elif attribute.get("value") is not None:
                value = str(attribute["value"])
                if attribute.get("unit"):
                    value = f"{value} {attribute['unit']}"
            else:
                continue
            items.append(
                {
                    "key": str(attribute.get("key") or ""),
                    "label": str(attribute["label"]),
                    "value": value,
                }
            )
        if items:
            label = _CAR_GROUP_LABELS.get(str(group.get("key")), str(group.get("key")))
            groups.append({"label": label, "items": items})
    return groups


def _gallery_images(gallery: dict[str, Any], image_size: str) -> list[ListingImage]:
    images: list[ListingImage] = []
    media = (gallery.get("media") or {}).get("images")
    if isinstance(media, list) and media:
        for image in media:
            if not isinstance(image, dict) or not isinstance(image.get("base"), str):
                continue
            url = _image_url(image["base"], image_size)
            images.append(ListingImage(key=str(image.get("mediaId") or url), url=url))
        return images
    for base in gallery.get("imageUrls") or []:
        if isinstance(base, str):
            url = _image_url(base, image_size)
            images.append(ListingImage(key=url, url=url))
    return images


def _image_url(base: str, image_size: str) -> str:
    if image_size == "original":
        url = base.split("?", 1)[0]
    else:
        url = base.replace("#", image_size)
    return f"https:{url}" if url.startswith("//") else url


def _seller(raw: dict[str, Any], base_url: str) -> dict[str, Any]:
    seller = {key: raw[key] for key in _SELLER_FIELDS if raw.get(key) not in (None, "")}
    if raw.get("phoneNumberHidden"):
        seller.pop("phoneNumber", None)
    for key in _SELLER_URL_FIELDS:
        value = raw.get(key)
        if isinstance(value, str) and value:
            seller[key] = value if value.startswith("http") else f"{base_url}{value}"
    location = raw.get("location") or {}
    if location.get("cityName"):
        seller["city"] = location["cityName"]
    return seller


class _ListingMarkup(HTMLParser):
    """Collects the description (sanitized) and the rendered attribute list."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attributes: list[dict[str, str]] = []
        self._html: list[str] = []
        self._text: list[str] = []
        self._open: list[str] = []
        self._description_depth = 0
        self._skip_depth = 0
        self._attribute_part: str | None = None
        self._attribute_depth = 0
        self._attribute_label = ""
        self._attribute_value = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._description_depth:
            self._description_start(tag)
        elif tag == "div" and attributes.get("data-collapsable") == "description":
            self._description_depth = 1
            return

        if self._attribute_part:
            if tag not in _VOID_TAGS:
                self._attribute_depth += 1
        elif tag == "div":
            css = attributes.get("class") or ""
            if "Attributes-module-label" in css:
                self._attribute_part, self._attribute_depth = "label", 1
                self._attribute_label = ""
            elif "Attributes-module-value" in css:
                self._attribute_part, self._attribute_depth = "value", 1
                self._attribute_value = ""

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._description_depth and not self._skip_depth and tag == "br":
            self._html.append("<br>")
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._description_depth:
            self._description_end(tag)
        if self._attribute_part and tag not in _VOID_TAGS:
            self._attribute_depth -= 1
            if self._attribute_depth == 0:
                if self._attribute_part == "value" and self._attribute_label:
                    self.attributes.append(
                        {
                            "key": "",
                            "label": _squash(self._attribute_label),
                            "value": _squash(self._attribute_value),
                        }
                    )
                    self._attribute_label = ""
                self._attribute_part = None

    def handle_data(self, data: str) -> None:
        if self._description_depth and not self._skip_depth:
            self._html.append(html.escape(data, quote=False))
            self._text.append(data)
        if self._attribute_part == "label":
            self._attribute_label += data
        elif self._attribute_part == "value":
            self._attribute_value += data

    def description_html(self) -> str:
        for tag in reversed(self._open):
            self._html.append(f"</{tag}>")
        self._open.clear()
        return "".join(self._html).strip()

    def description_text(self) -> str:
        text = "".join(self._text).replace("\r", "")
        lines = [" ".join(line.split()) for line in text.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    def _description_start(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            if tag == "br" and not self._skip_depth:
                self._html.append("<br>")
                self._text.append("\n")
            return
        self._description_depth += 1
        if self._skip_depth or tag in _SKIPPED_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if tag in _BLOCK_TAGS:
            self._text.append("\n")
        if tag in _ALLOWED_TAGS:
            self._html.append(f"<{tag}>")
            self._open.append(tag)

    def _description_end(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        self._description_depth -= 1
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._text.append("\n")
        if tag in self._open:
            while self._open:
                current = self._open.pop()
                self._html.append(f"</{current}>")
                if current == tag:
                    break


def _squash(value: str) -> str:
    return " ".join(value.split())
