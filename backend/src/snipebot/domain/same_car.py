"""The same car listed on several platforms, shown as one search result.

Dealers often put a car on Marktplaats, AutoScout24 and ViaBOVAG at once.
Search results carry no license plate on most platforms, so listings count
as the same car when, on different platforms:

- the build year and mileage are stated and equal (mileage is rarely equal
  by chance; dealers type it per car);
- they are in the same place, or their titles start alike (some platforms
  name a nearby village instead of the town);
- their prices differ at most ``MAX_PRICE_DIFFERENCE`` (dealers sometimes
  ask a little more on one platform).

A platform holds each car once, so a group has at most one listing per
platform; a listing joins the group whose price is closest. That keeps two
cars of one dealer with the same round mileage apart.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol

MAX_PRICE_DIFFERENCE = Decimal("0.06")
_TITLE_PREFIX = 24
_COUNTRY_SUFFIX = re.compile(r"\s*\([A-Z]{2}\)$")


class ListingLike(Protocol):
    marketplace: str
    title: str
    city: str | None
    current_price: Decimal | None
    attributes_json: str


def group_same_cars[T: ListingLike](rows: Iterable[T]) -> list[list[T]]:
    """Groups of listings of the same car, in the order of their first listing."""
    groups: list[list[T]] = []
    by_key: dict[tuple[str, str], list[list[T]]] = {}
    for row in rows:
        key = _car_key(row)
        if key is None:
            groups.append([row])
            continue
        candidates = [
            group
            for group in by_key.get(key, [])
            if all(other.marketplace != row.marketplace for other in group)
            and any(same_car(row, other) for other in group)
        ]
        if candidates:
            min(candidates, key=lambda group: _price_gap(row, group)).append(row)
            continue
        group = [row]
        groups.append(group)
        by_key.setdefault(key, []).append(group)
    return groups


def same_car(a: ListingLike, b: ListingLike) -> bool:
    if a.marketplace == b.marketplace:
        return False
    key = _car_key(a)
    if key is None or key != _car_key(b):
        return False
    if not (_same_place(a.city, b.city) or _title_prefix(a.title) == _title_prefix(b.title)):
        return False
    if a.current_price is None or b.current_price is None:
        return True
    low, high = sorted((a.current_price, b.current_price))
    return high - low <= high * MAX_PRICE_DIFFERENCE


def _car_key(row: ListingLike) -> tuple[str, str] | None:
    attributes = json.loads(row.attributes_json or "{}")
    mileage = str(attributes.get("mileage") or "")
    year = str(attributes.get("constructionYear") or "")
    if not mileage.isdigit() or int(mileage) < 1000 or not year:
        return None
    return year, str(int(mileage))


def _price_gap(row: ListingLike, group: list) -> Decimal:
    prices = [other.current_price for other in group if other.current_price is not None]
    if row.current_price is None or not prices:
        return Decimal(0)
    return min(abs(row.current_price - price) for price in prices)


def _same_place(a: str | None, b: str | None) -> bool:
    a, b = _place(a), _place(b)
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _place(city: str | None) -> str:
    return re.sub(r"[^a-z]", "", _COUNTRY_SUFFIX.sub("", city or "").lower())


def _title_prefix(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:_TITLE_PREFIX]
