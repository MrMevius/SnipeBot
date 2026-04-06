from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html import unescape

TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
PRICE_PATTERN = re.compile(
    r"(?:€\s*|EUR\s*)(\d{1,3}(?:[\.\s]\d{3})*(?:[\.,]\d{1,2})?|\d+(?:[\.,]\d{1,2})?)",
    re.IGNORECASE,
)
JSON_LD_PRICE_PATTERN = re.compile(
    r'"price"\s*:\s*"?(\d+(?:[\.,]\d{1,2})?)"?', re.IGNORECASE
)
META_PRICE_TAG_PATTERN = re.compile(r"<meta[^>]*>", re.IGNORECASE)
META_CONTENT_PATTERN = re.compile(r"content=['\"]([^'\"]+)['\"]", re.IGNORECASE)


def extract_title(html: str) -> str:
    match = TITLE_PATTERN.search(html)
    if not match:
        raise ValueError("Could not parse product title")
    title = " ".join(match.group(1).split())
    if not title:
        raise ValueError("Parsed empty product title")
    return title


def extract_price(html: str) -> Decimal:
    for candidate in _structured_price_candidates(html):
        price = _parse_decimal_candidate(candidate)
        if price is not None:
            return price

    match = PRICE_PATTERN.search(html)
    if match:
        price = _parse_decimal_candidate(match.group(1))
        if price is not None:
            return price

    raise ValueError("Could not parse product price")


def _structured_price_candidates(html: str) -> list[str]:
    normalized_html = _decode_markup_for_structured_price(html)

    candidates = [
        match.group(1)
        for match in JSON_LD_PRICE_PATTERN.finditer(normalized_html)
        if match.group(1)
    ]

    for meta_tag_match in META_PRICE_TAG_PATTERN.finditer(normalized_html):
        tag = meta_tag_match.group(0)
        if "product:price:amount" not in tag.lower():
            continue
        content_match = META_CONTENT_PATTERN.search(tag)
        if content_match and content_match.group(1):
            candidates.append(content_match.group(1))

    return candidates


def _decode_markup_for_structured_price(html: str) -> str:
    normalized = html
    for encoded, plain in (
        (r"\u0022", '"'),
        (r"\u003a", ":"),
        (r"\u002e", "."),
        (r"\u002c", ","),
    ):
        normalized = normalized.replace(encoded, plain)
        normalized = normalized.replace(encoded.upper(), plain)

    return unescape(normalized)


def _parse_decimal_candidate(raw_value: str) -> Decimal | None:
    cleaned = re.sub(r"[^\d\.,]", "", raw_value)
    if not cleaned:
        return None

    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            normalized = cleaned.replace(".", "").replace(",", ".")
        else:
            normalized = cleaned.replace(",", "")
    elif "," in cleaned:
        whole, _, decimal = cleaned.partition(",")
        if decimal and len(decimal) <= 2:
            normalized = f"{whole}.{decimal}"
        else:
            normalized = cleaned.replace(",", "")
    elif "." in cleaned:
        whole, _, decimal = cleaned.partition(".")
        if decimal and len(decimal) <= 2:
            normalized = cleaned
        else:
            normalized = cleaned.replace(".", "")
    else:
        normalized = cleaned

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


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
