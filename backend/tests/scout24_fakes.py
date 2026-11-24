"""Synthetic AutoTrack/AutoScout24 pages shaped like the real Next.js page data."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from snipebot.adapters.marketplaces.scout24 import AUTOTRACK, Scout24Site

IMAGE_BASE = "https://prod.pictures.autoscout24.net/listing-images"
TESLA = {"label": "Tesla", "value": 51520}
MODEL_3 = {"value": 74665, "label": "Model 3", "makeId": 51520, "modelLineId": None}


def _page(props: dict[str, Any]) -> str:
    data = {"props": {"pageProps": props}}
    # Next.js escapes "<" inside the JSON, so HTML in strings cannot end the script.
    payload = json.dumps(data).replace("<", "\\u003c")
    return (
        "<html><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        "</body></html>"
    )


def uuid(number: int) -> str:
    return f"00000000-0000-0000-0000-{number:012d}"


def search_listing(
    number: int,
    *,
    price: int = 34950,
    version: str = "Long Range RWD 78 kWh",
    range_km: int | None = 600,
    plate: str | None = "S-123-AB",
    registration: str = "03-2024",
    country: str = "NL",
    seller: str = "Dealer",
    site: Scout24Site = AUTOTRACK,
) -> dict[str, Any]:
    listing_id = uuid(number)
    details = [{"data": "12.345 km", "iconName": "mileage_odometer", "ariaLabel": "Kilometerstand"}]
    if range_km is not None:
        details.append({"data": f"{range_km} km actieradius", "iconName": "distance", "ariaLabel": "actieradius"})
    return {
        "id": listing_id,
        "title": "Tesla Model 3",
        "images": [f"{IMAGE_BASE}/{listing_id}_photo{n}.jpg/250x188.webp" for n in range(2)],
        "price": {"priceFormatted": f"€ {price}", "priceRaw": price},
        "url": f"{site.listing_prefix}tesla-model-3-cat_ma51520mo74665-{listing_id}",
        "vehicle": {
            "make": "Tesla",
            "model": "Model 3",
            "modelVersionInput": version,
            "transmission": "Automatisch",
            "fuel": "Elektrisch",
            "jsonLd": {"licensePlate": plate},
        },
        "location": {"countryCode": country, "zip": "8242 BA", "city": "LELYSTAD"},
        "seller": {"id": "1", "type": seller, "companyName": "EV Dealer B.V."},
        "tracking": {"firstRegistration": registration, "mileage": "12345", "price": str(price)},
        "vehicleDetails": details,
    }


def search_page(listings: list[dict[str, Any]], *, total: int | None = None, pages: int = 1) -> str:
    return _page(
        {
            "numberOfResults": len(listings) if total is None else total,
            "numberOfPages": pages,
            "listings": listings,
            "taxonomy": {
                "makesSorted": [{"label": "Polestar", "value": 51838}, TESLA],
                "models": {"51520": [MODEL_3, {"value": 75320, "label": "Model Y", "makeId": 51520}]},
            },
        }
    )


def listing_page(number: int, *, price: int = 34950, plate: str = "S-123-AB") -> str:
    listing_id = uuid(number)
    return _page(
        {
            "listingDetails": {
                "id": listing_id,
                "title": "Tesla Model 3",
                "description": "Nette auto.<br><strong>Dealer onderhouden</strong><script>x()</script>",
                "images": [f"{IMAGE_BASE}/{listing_id}_photo{n}.jpg/1280x960.webp" for n in range(3)],
                "prices": {"public": {"price": f"€ {price}", "priceRaw": price}},
                "vehicle": {
                    "licensePlate": plate,
                    "make": "Tesla",
                    "model": "Model 3",
                    "modelVersionInput": "Long Range RWD 78 kWh",
                    "mileageInKm": "12.345 km",
                    "firstRegistrationDate": "03/2024",
                    "numberOfSeats": 5,
                    "fuelCategory": {"raw": "E", "formatted": "Elektrisch"},
                    "electricRangeWithFallback": {"raw": 600, "formatted": "600 km", "isFallback": False},
                    "hadAccident": False,
                    "equipment": {
                        "comfortAndConvenience": [{"id": "Airconditioning"}, {"id": "Stoelverwarming"}],
                        "safetyAndSecurity": [{"id": "ABS"}],
                    },
                },
                "location": {"zip": "8242 BA", "city": "LELYSTAD", "street": "Kempenaar 1"},
                "seller": {
                    "type": "Dealer",
                    "companyName": "EV Dealer B.V.",
                    "contactName": "Jan",
                    "phones": [{"phoneType": "Office", "formattedNumber": "+31 (0)320 - 000000"}],
                    "links": {"infoPage": "https://www.autoscout24.nl/autobedrijven/ev-dealer"},
                },
                "ratings": {"ratingsCount": 148, "ratingsAverage": "4,8"},
                "dpvStatistics": {"interaction": 1397, "favorites": 37},
                "createdTimestampWithOffset": "2026-11-05T11:26:29.042Z",
            }
        }
    )


class FakeScout24:
    """Serves search pages (queued per page number), listing pages and photos."""

    def __init__(self, site: Scout24Site = AUTOTRACK) -> None:
        self.site = site
        self.search_pages: list[dict[int, str]] = []
        self.listing_pages: dict[str, str | Exception] = {}
        self.requests: list[str] = []
        self.image_requests: list[str] = []
        self.error: Exception | None = None

    def __call__(self, url: str) -> str:
        self.requests.append(url)
        if self.error is not None:
            raise self.error
        parts = urlsplit(url)
        if parts.path.startswith(self.site.listing_prefix):
            listing_id = parts.path.rsplit("-", 5)
            key = "-".join(listing_id[-5:])
            page = self.listing_pages.get(key)
            if page is None:
                page = listing_page(int(key[-12:]))
            if isinstance(page, Exception):
                raise page
            return page
        params = parse_qs(parts.query)
        if "page" not in params:
            # Taxonomy lookups.
            return search_page([])
        number = int(params["page"][0])
        pages = self.search_pages[0] if self.search_pages else {1: search_page([])}
        page = pages[number]
        if number == max(pages):
            if self.search_pages:
                self.search_pages.pop(0)
        return page

    def image(self, url: str) -> bytes:
        self.image_requests.append(url)
        return f"jpeg:{url}".encode()
