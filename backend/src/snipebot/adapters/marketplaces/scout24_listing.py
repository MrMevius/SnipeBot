"""AutoTrack and AutoScout24 listing pages: full details for the local archive.

``listingDetails`` in the page data holds the description (HTML), vehicle data,
equipment, dealer and photo URLs. Photos are stored in their uploaded size by
dropping the resize suffix. A removed listing redirects to a search page, which
has no ``listingDetails``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from snipebot.adapters.marketplaces.scout24 import (
    IMAGE_HOSTS,
    USER_AGENT,
    Fetcher,
    Scout24Error,
    Scout24Site,
    city_label,
    http_fetch,
    normalize_plate,
    original_image_url,
    page_props,
)
from snipebot.adapters.marketplaces.marktplaats_listing import (
    MAX_IMAGE_BYTES,
    ListingDetail,
    ListingImage,
    sanitize_description,
)

_IMAGE_KEY = re.compile(r"/([^/]+)\.jpe?g$", re.IGNORECASE)

# (group label, [(label, vehicle field)]); values are the site's formatted strings.
_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Basis",
        (
            ("Kenteken", "licensePlate"),
            ("Uitvoering", "modelVersionInput"),
            ("Eerste registratie", "firstRegistrationDate"),
            ("Kilometerstand", "mileageInKm"),
            ("Carrosserie", "bodyType"),
            ("Kleur", "bodyColor"),
            ("Lak", "paintType"),
            ("Bekleding", "upholstery"),
            ("Kleur interieur", "upholsteryColor"),
            ("Zitplaatsen", "numberOfSeats"),
            ("Deuren", "numberOfDoors"),
        ),
    ),
    (
        "Techniek",
        (
            ("Brandstof", "fuelCategory"),
            ("Vermogen", "powerInKw"),
            ("Vermogen (pk)", "powerInHp"),
            ("Transmissie", "transmissionType"),
            ("Aandrijving", "driveTrain"),
            ("Actieradius", "electricRangeWithFallback"),
            ("Gewicht", "weight"),
        ),
    ),
    (
        "Historie",
        (
            ("Vorige eigenaren", "noOfPreviousOwners"),
            ("APK tot", "nextVehicleSafetyInspection"),
            ("Herkomst", "originalMarket"),
            ("Volledige onderhoudshistorie", "hasFullServiceHistory"),
            ("Ongeval gehad", "hadAccident"),
        ),
    ),
)

_SELLER_TYPES = {"Dealer": "TRADER", "Private": "CONSUMER", "PrivateSeller": "CONSUMER"}

ImageFetcher = Callable[[str], bytes]


def validate_listing_url(url: str, site: Scout24Site) -> str:
    parts = urlsplit(url.strip())
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in site.hosts
        or not parts.path.startswith(site.listing_prefix)
    ):
        raise Scout24Error("invalid_url", f"Not a {site.label} listing URL")
    return f"{site.base_url}{parts.path}"


def fetch_listing(url: str, site: Scout24Site, *, fetch: Fetcher | None = None) -> ListingDetail:
    page_url = validate_listing_url(url, site)
    page_html = fetch(page_url) if fetch is not None else http_fetch(page_url, site.label)
    return parse_listing_page(page_html, url=page_url, site=site)


def parse_listing_page(page_html: str, *, url: str, site: Scout24Site) -> ListingDetail:
    props = page_props(page_html, site.label)
    details = props.get("listingDetails")
    if not isinstance(details, dict):
        if "listings" in props or "numberOfResults" in props:
            raise Scout24Error("gone", f"{site.label} listing was removed")
        raise Scout24Error("parse_error", f"{site.label} listing data not found")
    item_id = details.get("id")
    vehicle = details.get("vehicle") or {}
    if not isinstance(item_id, str):
        raise Scout24Error("parse_error", f"{site.label} listing has no id")
    title = " ".join(
        str(part).strip()
        for part in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput"))
        if part
    ) or str(details.get("title") or "").strip()

    public_price = ((details.get("prices") or {}).get("public") or {}).get("priceRaw")
    location = details.get("location") or {}
    description_html, description_text = sanitize_description(str(details.get("description") or ""))
    statistics = details.get("dpvStatistics") or {}
    city = city_label(location, site)

    return ListingDetail(
        item_id=item_id,
        title=title,
        url=url,
        price=Decimal(int(public_price)) if isinstance(public_price, int) and public_price > 0 else None,
        price_type=None,
        category=[str(name) for name in (vehicle.get("make"), vehicle.get("model")) if name],
        description_html=description_html,
        description_text=description_text,
        attribute_groups=_attribute_groups(vehicle),
        images=_images(details.get("images")),
        seller=_seller(details.get("seller") or {}, details.get("ratings") or {}, location, city),
        stats={
            key: value
            for key, value in (
                ("viewCount", statistics.get("interaction")),
                ("favoritedCount", statistics.get("favorites")),
                ("since", details.get("createdTimestampWithOffset")),
            )
            if value is not None
        },
        highlights=[],
        city=city,
        postcode=location.get("zip") or None,
        is_reserved=False,
        extra={"license_plate": normalize_plate(vehicle.get("licensePlate"))},
    )


def image_fetch(url: str) -> bytes:
    """Download a listing photo; only the AutoScout24 image host is allowed."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        raise Scout24Error("invalid_url", "Unexpected image host")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except HTTPError as exc:
        kind = "blocked" if exc.code in {403, 429} else "fetch_error"
        raise Scout24Error(kind, f"Image request returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise Scout24Error("fetch_error", f"Image request failed: {exc}") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise Scout24Error("fetch_error", "Image is too large")
    return data


def _attribute_groups(vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for label, fields in _GROUPS:
        items = [
            {"key": field, "label": item_label, "value": value}
            for item_label, field in fields
            if (value := _display(vehicle.get(field))) is not None
        ]
        if items:
            groups.append({"label": label, "items": items})
    equipment: list[str] = []
    for entries in (vehicle.get("equipment") or {}).values():
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("id"):
                equipment.append(str(entry["id"]))
    if equipment:
        groups.append(
            {"label": "Opties", "items": [{"key": "options", "label": "Opties", "value": ", ".join(equipment)}]}
        )
    return groups


def _display(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("formatted")
    if isinstance(value, bool):
        return "Ja" if value else "Nee"
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _images(raw: Any) -> list[ListingImage]:
    images: list[ListingImage] = []
    for url in raw or []:
        if not isinstance(url, str):
            continue
        original = original_image_url(url)
        match = _IMAGE_KEY.search(original)
        images.append(ListingImage(key=match.group(1) if match else original, url=original))
    return images


def _seller(
    raw: dict[str, Any], ratings: dict[str, Any], location: dict[str, Any], city: str | None
) -> dict[str, Any]:
    seller: dict[str, Any] = {}
    if raw.get("companyName"):
        seller["name"] = str(raw["companyName"])
    if raw.get("contactName"):
        seller["contactName"] = str(raw["contactName"])
    seller_type = raw.get("type")
    if seller_type:
        seller["sellerType"] = _SELLER_TYPES.get(seller_type, seller_type)
    if city:
        seller["city"] = city
    address = ", ".join(
        str(part) for part in (location.get("street"), location.get("zip"), city) if part
    )
    if address:
        seller["address"] = address
    phones = [
        str(phone["formattedNumber"])
        for phone in raw.get("phones") or []
        if isinstance(phone, dict) and phone.get("formattedNumber")
    ]
    if phones:
        seller["phoneNumber"] = phones[0]
    info_page = (raw.get("links") or {}).get("infoPage")
    if isinstance(info_page, str) and info_page.startswith("https://"):
        seller["sellerProfileUrl"] = info_page
    if ratings.get("ratingsAverage") and ratings.get("ratingsCount"):
        seller["rating"] = f"{ratings['ratingsAverage']} ({ratings['ratingsCount']} reviews)"
    return seller
