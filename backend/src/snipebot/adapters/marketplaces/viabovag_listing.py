"""ViaBOVAG listing pages (``/auto/aanbod/...``): full details for the local archive.

The page's flight data holds an object with the vehicle id, the advertisement
(title, dealer comments as a text record, price, dealer, BOVAG certainties,
photos) and the vehicle specifications in labelled groups.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from snipebot.adapters.marketplaces.marktplaats_listing import (
    MAX_IMAGE_BYTES,
    ListingDetail,
    ListingImage,
    sanitize_description,
)
from snipebot.adapters.marketplaces.scout24 import normalize_plate
from snipebot.adapters.marketplaces.viabovag import (
    BASE_URL,
    IMAGE_HOSTS,
    USER_AGENT,
    VIABOVAG_HOSTS,
    Fetcher,
    ViaBovagError,
    find_object,
    http_fetch,
    parse_flight,
)

_IMAGE_KEY = re.compile(r"/vehicles-media/([^/]+/[^/?]+)$")
_PRICE = re.compile(r"[\d.]+")


def validate_listing_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in VIABOVAG_HOSTS
        or not parts.path.startswith("/auto/aanbod/")
    ):
        raise ViaBovagError("invalid_url", "Not a viabovag.nl listing URL")
    return f"{BASE_URL}{parts.path}"


def fetch_listing(url: str, *, fetch: Fetcher | None = None) -> ListingDetail:
    page_url = validate_listing_url(url)
    return parse_listing_page((fetch or http_fetch)(page_url), url=page_url)


def parse_listing_page(page_html: str, *, url: str) -> ListingDetail:
    records = parse_flight(page_html)
    detail = None
    for record in records.values():
        detail = find_object(record, "id", "advertisement", "vehicle")
        if detail is not None:
            break
    if detail is None:
        raise ViaBovagError("parse_error", "ViaBOVAG listing data not found (layout change)")
    advertisement = detail.get("advertisement") or {}
    specs = detail.get("vehicle") or {}
    general = specs.get("general") or {}

    comments = _value(advertisement.get("comments"))
    if comments and comments.startswith("$") and isinstance(records.get(comments[1:]), str):
        comments = records[comments[1:]]
    description_html, description_text = sanitize_description(comments or "")

    company = advertisement.get("company") or {}
    address = company.get("address") or {}
    city = str(address.get("city")).title() if address.get("city") else None
    price_text = _value(advertisement.get("price")) or ""
    price_match = _PRICE.search(price_text)
    price = Decimal(price_match.group(0).replace(".", "")) if price_match else None

    groups: list[dict[str, Any]] = []
    for group in specs.get("specificationGroups") or []:
        items = [
            {"key": "", "label": str(item["label"]), "value": str(item["formattedValue"])}
            for item in group.get("specifications") or []
            if item.get("hasValue") and item.get("label") and item.get("formattedValue")
        ]
        if items:
            groups.append({"label": str(group.get("name") or "Specificaties"), "items": items})
    plate = normalize_plate(_value((specs.get("identification") or {}).get("vehicleLicencePlate")))
    if plate:
        groups.insert(0, {"label": "Kenteken", "items": [{"key": "licensePlate", "label": "Kenteken", "value": plate}]})
    certainties = [
        str(item["label"])
        for item in (advertisement.get("certainties") or {}).values()
        if isinstance(item, dict) and item.get("value") is True and item.get("label")
    ]
    accessories = [
        str(item["formattedValue"])
        for item in specs.get("accessories") or []
        if item.get("hasValue") and item.get("formattedValue")
    ]
    if accessories:
        groups.append(
            {"label": "Opties", "items": [{"key": "options", "label": "Opties", "value": ", ".join(accessories)}]}
        )

    return ListingDetail(
        item_id=str(detail["id"]),
        title=_value(advertisement.get("title")) or "",
        url=url,
        price=price if price else None,
        price_type=None,
        category=[value for value in (_value(general.get("brand")), _value(general.get("model"))) if value],
        description_html=description_html,
        description_text=description_text,
        attribute_groups=groups,
        images=_images(advertisement.get("media")),
        seller=_seller(company, city),
        stats={},
        highlights=certainties,
        city=city,
        postcode=address.get("postalCode") or address.get("zipCode") or None,
        is_reserved=False,
        extra={"license_plate": plate},
    )


def image_fetch(url: str) -> bytes:
    """Download a listing photo; only ViaBOVAG's image storage is allowed."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        raise ViaBovagError("invalid_url", "Unexpected image host")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except HTTPError as exc:
        kind = "blocked" if exc.code in {403, 429} else "fetch_error"
        raise ViaBovagError(kind, f"Image request returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise ViaBovagError("fetch_error", f"Image request failed: {exc}") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ViaBovagError("fetch_error", "Image is too large")
    return data


def _value(field: Any) -> str | None:
    if isinstance(field, dict):
        return str(field["formattedValue"]) if field.get("hasValue") and field.get("formattedValue") else None
    return None


def _images(media: Any) -> list[ListingImage]:
    images: list[ListingImage] = []
    for item in media or []:
        if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("url"), str):
            key = _IMAGE_KEY.search(item["url"])
            images.append(ListingImage(key=key.group(1) if key else item["url"], url=item["url"]))
    return images


def _seller(company: dict[str, Any], city: str | None) -> dict[str, Any]:
    seller: dict[str, Any] = {"sellerType": "TRADER"}
    if company.get("name"):
        seller["name"] = str(company["name"])
    address = company.get("address") or {}
    street = " ".join(
        str(part) for part in (address.get("street"), address.get("houseNumber")) if part
    )
    full = ", ".join(part for part in (street, str(address.get("postalCode") or ""), city or "") if part)
    if full:
        seller["address"] = full
    if city:
        seller["city"] = city
    phone = (company.get("contact") or {}).get("phoneNumber")
    if phone:
        seller["phoneNumber"] = str(phone)
    return seller
