"""Resolve the variant of search results for the "Uitvoering" filter.

Search results often lack the power or battery that tells variants apart
(Marktplaats, 2dehands and Kleinanzeigen only show them on the listing page).
A listing whose search data does not pin down one variant is resolved, in
order, from:

1. the variant cache (``MarketplaceVariantCache``), unless the title changed or
   an unresolved entry is older than ``RECHECK_UNRESOLVED``;
2. the archived listing page (``MarketplaceItem``), when the archive has it;
3. the listing page itself, fetched with the platform's archive source. At
   most ``max_fetches`` pages per check, ``FETCH_DELAY_SECONDS`` apart; a
   baseline check has no limit, so later checks only see new listings.

The result is written to ``listing.attributes["variant"]`` (comma-separated
keys), where ``search_filters.check_listing`` reads it.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces.base import Listing, MarketplaceError
from snipebot.adapters.marketplaces.marktplaats_listing import ListingDetail
from snipebot.domain.car_variants import detail_variants, listing_variants
from snipebot.persistence.models import MarketplaceItem, MarketplaceVariantCache

logger = logging.getLogger(__name__)

MAX_FETCHES_PER_CHECK = 40
FETCH_DELAY_SECONDS = 2.0
RECHECK_UNRESOLVED = timedelta(days=7)


def apply_search_data(listings: list[Listing]) -> None:
    """Variants from the search data alone (previews, which fetch no pages)."""
    for listing in listings:
        _store(listing, listing_variants(listing))


def resolve_variants(
    db_session: Session,
    marketplace: str,
    listings: list[Listing],
    *,
    fetch_detail: Callable[[str], ListingDetail] | None = None,
    max_fetches: int | None = MAX_FETCHES_PER_CHECK,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    open_listings: list[tuple[Listing, frozenset[str] | None]] = []
    for listing in listings:
        found = listing_variants(listing)
        _store(listing, found)
        if found is None or len(found) > 1:
            open_listings.append((listing, found))
    if not open_listings:
        return

    ids = [(marketplace, listing.item_id) for listing, _ in open_listings]
    cache = {
        row.item_id: row
        for row in db_session.scalars(
            select(MarketplaceVariantCache).where(
                tuple_(MarketplaceVariantCache.marketplace, MarketplaceVariantCache.item_id).in_(ids)
            )
        )
    }
    archived = {
        item.item_id: item
        for item in db_session.scalars(
            select(MarketplaceItem).where(
                tuple_(MarketplaceItem.marketplace, MarketplaceItem.item_id).in_(ids),
                MarketplaceItem.archived_at.is_not(None),
            )
        )
    }

    fetches = 0
    for listing, found in open_listings:
        row = cache.get(listing.item_id)
        if row is not None and _fresh(row, listing, now):
            _store(listing, _narrow(found, _parse(row.variants)))
            continue
        item = archived.get(listing.item_id)
        if item is not None and item.listing_title == listing.title:
            resolved = detail_variants(item.title, json.loads(item.attribute_groups_json or "[]"))
        elif fetch_detail is not None and (max_fetches is None or fetches < max_fetches):
            if fetches:
                sleep(FETCH_DELAY_SECONDS)
            fetches += 1
            try:
                detail = fetch_detail(listing.url)
            except MarketplaceError as exc:
                logger.info(
                    "variant.fetch_failed marketplace=%s item_id=%s reason=%s",
                    marketplace,
                    listing.item_id,
                    exc,
                )
                if exc.kind == "blocked":
                    fetch_detail = None
                continue
            resolved = detail_variants(detail.title, detail.attribute_groups)
        else:
            continue
        row = _save(db_session, row, marketplace, listing, resolved, now)
        cache[listing.item_id] = row
        _store(listing, _narrow(found, resolved))
    if fetches:
        logger.info("variant.pages_fetched marketplace=%s count=%s", marketplace, fetches)


def _fresh(row: MarketplaceVariantCache, listing: Listing, now: datetime) -> bool:
    if row.title != listing.title[:512]:
        return False
    checked = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=UTC)
    return row.variants is not None or now - checked < RECHECK_UNRESOLVED


def _save(
    db_session: Session,
    row: MarketplaceVariantCache | None,
    marketplace: str,
    listing: Listing,
    resolved: frozenset[str] | None,
    now: datetime,
) -> MarketplaceVariantCache:
    if row is None:
        row = MarketplaceVariantCache(marketplace=marketplace, item_id=listing.item_id)
        db_session.add(row)
    row.title = listing.title[:512]
    row.variants = ",".join(sorted(resolved)) if resolved else None
    row.checked_at = now
    return row


def _narrow(found: frozenset[str] | None, resolved: frozenset[str] | None) -> frozenset[str] | None:
    """The listing page knows more; the search data still narrows it when they agree."""
    if found and resolved and found & resolved:
        return found & resolved
    return resolved or found


def _parse(value: str | None) -> frozenset[str] | None:
    return frozenset(value.split(",")) if value else None


def _store(listing: Listing, variants: frozenset[str] | None) -> None:
    if variants:
        listing.attributes["variant"] = ",".join(sorted(variants))
    else:
        listing.attributes.pop("variant", None)
