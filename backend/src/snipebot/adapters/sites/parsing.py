from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
PRICE_PATTERN = re.compile(r"(?:€|EUR\s*)(\d{1,4}(?:[\.,]\d{1,2})?)", re.IGNORECASE)


def extract_title(html: str) -> str:
    match = TITLE_PATTERN.search(html)
    if not match:
        raise ValueError("Could not parse product title")
    title = " ".join(match.group(1).split())
    if not title:
        raise ValueError("Parsed empty product title")
    return title


def extract_price(html: str) -> Decimal:
    match = PRICE_PATTERN.search(html)
    if not match:
        raise ValueError("Could not parse product price")

    candidate = match.group(1).replace(".", "").replace(",", ".")
    try:
        return Decimal(candidate)
    except InvalidOperation as exc:
        raise ValueError("Could not parse product price") from exc


def infer_availability(html: str) -> str:
    lowered = html.lower()
    if any(
        token in lowered
        for token in ("out of stock", "uitverkocht", "niet op voorraad")
    ):
        return "out_of_stock"
    if any(token in lowered for token in ("in stock", "op voorraad", "beschikbaar")):
        return "in_stock"
    return "unknown"
