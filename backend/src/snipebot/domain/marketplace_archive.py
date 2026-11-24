"""Local archive of marketplace listings.

Every listing a saved search records is archived: the worker fetches the
listing page, stores its details and downloads all photos. The archive is kept
independently of the searches, so deleting a search keeps its listings.

A listing is fetched again when its price or title changes in the search
results, and otherwise weekly while it is online. A new version is stored only
when the content (title, price, description, attributes, seller, photos)
actually changed. Photos are only added, never deleted: a photo that disappears
from the listing is marked as removed.

Each platform has an ``ArchiveSource`` that fetches its listing pages and
photos. Fetching is throttled (one listing per few seconds, a time budget per
worker tick) and backs off per platform when that platform blocks requests.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces import scout24_listing
from snipebot.adapters.marketplaces.platforms import SHARED_LISTING_IDS
from snipebot.adapters.marketplaces.scout24 import SITES, normalize_plate
from snipebot.adapters.marketplaces.base import Listing, MarketplaceError
from snipebot.adapters.marketplaces.marktplaats import Fetcher
from snipebot.adapters.marketplaces.marktplaats_listing import (
    ImageFetcher,
    ListingDetail,
    fetch_listing,
    image_fetch,
)
from snipebot.core.config import Settings
from snipebot.core.metrics import metrics
from snipebot.persistence.models import (
    MarketplaceItem,
    MarketplaceItemImage,
    MarketplaceItemPrice,
    MarketplaceItemVersion,
    MarketplaceListing,
    MarketplaceSearch,
)

logger = logging.getLogger(__name__)

# Platforms whose listings are archived.
ARCHIVE_MARKETPLACES = ("marktplaats", "autoscout24", "autotrack")
DUE_BATCH_SIZE = 50
MAX_FETCH_FAILURES = 5
IMAGE_DELAY_SECONDS = 0.2
INCOMPLETE_RETRY = timedelta(hours=1)
SORT_COLUMNS = ("first_seen", "last_seen", "price", "title")

# Path segments: Marktplaats ids ("m123"), AutoTrack UUIDs, platform keys.
_SAFE_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# Per platform: blocked until, consecutive blocks.
_block_state: dict[str, dict[str, Any]] = {}


@dataclass(slots=True)
class ArchiveSource:
    """Fetches listing pages and photos of one platform."""

    fetch_detail: Callable[[str], ListingDetail]
    fetch_image: ImageFetcher


def build_sources(
    settings: Settings,
    *,
    fetch: Fetcher | None = None,
    image_fetcher: ImageFetcher | None = None,
) -> dict[str, ArchiveSource]:
    """Archive sources per platform; ``fetch``/``image_fetcher`` replace Marktplaats I/O."""
    sources = {
        "marktplaats": ArchiveSource(
            fetch_detail=lambda url: fetch_listing(
                url, fetch=fetch, image_size=settings.marketplace_archive_image_size
            ),
            fetch_image=image_fetcher or image_fetch,
        )
    }
    for key, site in SITES.items():
        sources[key] = ArchiveSource(
            fetch_detail=lambda url, site=site: scout24_listing.fetch_listing(url, site),
            fetch_image=scout24_listing.image_fetch,
        )
    return sources


class ArchiveStore:
    """Photo files under ``<root>/<platform>/<item id>/<sha256>.jpg``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, marketplace: str, item_id: str, data: bytes) -> tuple[str, str, int]:
        sha = hashlib.sha256(data).hexdigest()
        relative = f"{_safe_segment(marketplace)}/{_safe_segment(item_id)}/{sha}.jpg"
        path = self.root / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
        return relative, sha, len(data)

    def path(self, relative: str) -> Path:
        root = self.root.resolve()
        path = (root / relative).resolve()
        if root not in path.parents:
            raise ValueError("Path outside the archive")
        return path

    def delete_item(self, marketplace: str, item_id: str) -> None:
        shutil.rmtree(
            self.root / _safe_segment(marketplace) / _safe_segment(item_id), ignore_errors=True
        )


@dataclass(slots=True)
class ArchiveUsage:
    items: int
    images: int
    bytes: int


def build_store(settings: Settings) -> ArchiveStore:
    return ArchiveStore(settings.marketplace_archive_dir)


# --- Observations from saved searches ---------------------------------------


def observe_listings(
    db_session: Session, search: MarketplaceSearch, listings: list[Listing], now: datetime
) -> None:
    """Create archive items for new listings and schedule re-fetches on changes."""
    if not listings:
        return
    items = _items_by_key(db_session, [(listing.marketplace, listing.item_id) for listing in listings])
    for listing in listings:
        key = (listing.marketplace, listing.item_id)
        item = items.get(key) or _adopt_shared_item(db_session, listing)
        if item is not None:
            items[key] = item
        if item is None:
            item = _new_item(
                search.owner_id, listing.marketplace, listing.item_id, listing.url, listing.title, now
            )
            item.license_plate = listing.license_plate
            item.price = listing.price
            item.price_type = listing.price_type
            item.thumbnail_url = listing.image_url
            item.city = listing.city
            item.summary_attributes_json = json.dumps(listing.attributes, ensure_ascii=False)
            if listing.price is not None:
                item.prices.append(MarketplaceItemPrice(price=listing.price, observed_at=now))
            db_session.add(item)
            items[key] = item
            continue

        item.last_seen_at = now
        item.license_plate = item.license_plate or listing.license_plate
        item.thumbnail_url = listing.image_url or item.thumbnail_url
        item.summary_attributes_json = json.dumps(listing.attributes, ensure_ascii=False)
        refetch = False
        if item.gone_at is not None:
            item.gone_at = None
            if item.status == "gone":
                item.status = "archived" if item.archived_at else "pending"
            refetch = True
        if listing.price is not None and listing.price != item.price:
            item.prices.append(MarketplaceItemPrice(price=listing.price, observed_at=now))
            item.price = listing.price
            item.price_type = listing.price_type
            refetch = True
        if listing.title[:512] != item.listing_title:
            item.listing_title = listing.title[:512]
            refetch = True
        if refetch:
            item.next_fetch_at = now


def mark_listings_missing(
    db_session: Session, marketplace: str, item_ids: list[str], now: datetime
) -> None:
    """A search no longer shows these listings: check whether they still exist."""
    if not item_ids:
        return
    for item in _items_by_key(db_session, [(marketplace, item_id) for item_id in item_ids]).values():
        if item.gone_at is None and (item.next_fetch_at is None or _aware(item.next_fetch_at) > now):
            item.next_fetch_at = now


def backfill_items(db_session: Session) -> int:
    """Create archive items for recorded search listings that have none yet."""
    _backfill_license_plates(db_session)
    archived = (
        select(MarketplaceItem.id)
        .where(
            MarketplaceItem.marketplace == MarketplaceListing.marketplace,
            MarketplaceItem.item_id == MarketplaceListing.item_id,
        )
        .exists()
    )
    rows = db_session.execute(
        select(MarketplaceListing, MarketplaceSearch.owner_id)
        .join(MarketplaceSearch, MarketplaceSearch.id == MarketplaceListing.search_id)
        .where(MarketplaceListing.marketplace.in_(ARCHIVE_MARKETPLACES), ~archived)
        .order_by(MarketplaceListing.first_seen_at.asc())
    ).all()
    created: dict[tuple[str, str], MarketplaceItem] = {}
    now = datetime.now(UTC)
    for listing, owner_id in rows:
        key = (listing.marketplace, listing.item_id)
        if key in created:
            continue
        item = _new_item(
            owner_id, listing.marketplace, listing.item_id, listing.url, listing.title, now
        )
        item.first_seen_at = listing.first_seen_at
        item.last_seen_at = listing.last_seen_at
        item.price = listing.current_price
        item.price_type = listing.price_type
        item.thumbnail_url = listing.image_url
        item.city = listing.city
        item.summary_attributes_json = listing.attributes_json or "{}"
        for point in listing.prices:
            item.prices.append(
                MarketplaceItemPrice(price=point.price, observed_at=point.observed_at)
            )
        db_session.add(item)
        created[key] = item
    if created:
        db_session.commit()
        logger.info("marketplace_archive.backfill created=%s", len(created))
    return len(created)


# --- Worker ------------------------------------------------------------------


def run_due_archive_fetches(
    db_session: Session,
    settings: Settings,
    *,
    fetch: Fetcher | None = None,
    image_fetcher: ImageFetcher | None = None,
    sources: dict[str, ArchiveSource] | None = None,
    store: ArchiveStore | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    if not settings.marketplace_archive_enabled:
        return 0
    backfill_items(db_session)

    now = datetime.now(UTC)
    sources = sources or build_sources(settings, fetch=fetch, image_fetcher=image_fetcher)
    available = [key for key in sources if not _is_blocked(key, now)]
    if not available:
        return 0

    items = list(
        db_session.scalars(
            select(MarketplaceItem)
            .where(
                MarketplaceItem.marketplace.in_(available),
                MarketplaceItem.next_fetch_at.is_not(None),
                MarketplaceItem.next_fetch_at <= now,
            )
            .order_by(MarketplaceItem.next_fetch_at.asc(), MarketplaceItem.id.asc())
            .limit(DUE_BATCH_SIZE)
        ).all()
    )
    store = store or build_store(settings)
    started = clock()
    processed = 0
    for item in items:
        marketplace = item.marketplace
        if _is_blocked(marketplace, datetime.now(UTC)):
            continue
        if processed and clock() - started >= settings.marketplace_archive_tick_budget_seconds:
            break
        if processed:
            sleep(settings.marketplace_archive_delay_seconds)
        processed += 1
        item_id = item.id
        try:
            archive_item(
                db_session,
                item,
                settings,
                source=sources[marketplace],
                store=store,
                sleep=sleep,
            )
            db_session.commit()
            _block_state.pop(marketplace, None)
        except Exception as exc:
            if isinstance(exc, MarketplaceError) and exc.kind == "blocked":
                # Keep the photos stored so far; the listing stays due.
                db_session.commit()
                _record_block(marketplace, str(exc), settings)
                continue
            db_session.rollback()
            metrics.inc("marketplace.archive_unhandled_error")
            logger.exception(
                "marketplace_archive.unhandled_error item=%s reason=%s", item_id, exc
            )
            failed = db_session.get(MarketplaceItem, item_id)
            if failed is not None:
                _record_fetch_failure(failed, str(exc), datetime.now(UTC), settings)
                db_session.commit()
    return processed


def archive_item(
    db_session: Session,
    item: MarketplaceItem,
    settings: Settings,
    *,
    source: ArchiveSource,
    store: ArchiveStore,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Fetch and store one listing. Raises ``MarketplaceError`` when blocked."""
    now = datetime.now(UTC)
    try:
        detail = source.fetch_detail(item.url)
        if detail.item_id != item.item_id:
            raise MarketplaceError("parse_error", "Listing page shows another listing")
    except MarketplaceError as exc:
        if exc.kind in {"gone", "invalid_url"}:
            item.status = "gone"
            item.gone_at = item.gone_at or now
            item.next_fetch_at = None
            item.fetch_failure_count = 0
            metrics.inc("marketplace.archive_gone")
            logger.info("marketplace_archive.gone item_id=%s", item.item_id)
            return "gone"
        if exc.kind == "blocked":
            raise
        _record_fetch_failure(item, str(exc), now, settings)
        return "failed"

    missing = _sync_images(item, detail, source.fetch_image, store, sleep, now)
    _apply_detail(db_session, item, detail, now)
    item.next_fetch_at = now + (
        INCOMPLETE_RETRY
        if missing
        else timedelta(days=max(1, settings.marketplace_archive_refresh_days))
    )
    metrics.inc("marketplace.archive_fetched")
    logger.info(
        "marketplace_archive.fetched item_id=%s images=%s missing=%s versions=%s",
        item.item_id,
        len(detail.images),
        missing,
        len(item.versions),
    )
    return "archived"


def _sync_images(
    item: MarketplaceItem,
    detail: ListingDetail,
    image_fetcher: ImageFetcher,
    store: ArchiveStore,
    sleep: Callable[[float], None],
    now: datetime,
) -> int:
    existing = {image.source_key: image for image in item.images}
    seen: set[str] = set()
    missing = 0
    for position, image in enumerate(detail.images):
        seen.add(image.key)
        row = existing.get(image.key)
        if row is not None:
            row.position = position
            row.removed_at = None
            continue
        try:
            data = image_fetcher(image.url)
        except MarketplaceError as exc:
            if exc.kind == "blocked":
                raise
            missing += 1
            logger.warning(
                "marketplace_archive.image_failed item_id=%s reason=%s", item.item_id, exc
            )
            continue
        relative, sha, size = store.save(item.marketplace, item.item_id, data)
        row = MarketplaceItemImage(
            source_key=image.key[:255],
            source_url=image.url,
            sha256=sha,
            file_path=relative,
            size_bytes=size,
            position=position,
            first_seen_at=now,
        )
        item.images.append(row)
        existing[image.key] = row
        sleep(IMAGE_DELAY_SECONDS)
    for row in item.images:
        if row.source_key not in seen and row.removed_at is None:
            row.removed_at = now
    return missing


def _apply_detail(
    db_session: Session, item: MarketplaceItem, detail: ListingDetail, now: datetime
) -> None:
    if detail.price is not None and detail.price != item.price:
        item.prices.append(MarketplaceItemPrice(price=detail.price, observed_at=now))
    item.price = detail.price
    item.price_type = detail.price_type
    item.title = detail.title[:512]
    item.url = detail.url
    item.city = detail.city or item.city
    item.postcode = detail.postcode
    item.category_json = json.dumps(detail.category, ensure_ascii=False)
    item.description_html = detail.description_html
    item.description_text = detail.description_text
    item.attribute_groups_json = json.dumps(detail.attribute_groups, ensure_ascii=False)
    item.seller_json = json.dumps(detail.seller, ensure_ascii=False)
    item.stats_json = json.dumps(detail.stats, ensure_ascii=False)
    item.highlights_json = json.dumps(detail.highlights, ensure_ascii=False)
    item.is_reserved = detail.is_reserved
    item.license_plate = (
        detail.extra.get("license_plate")
        or plate_from_attributes(detail.attribute_groups)
        or item.license_plate
    )
    item.status = "archived"
    item.archived_at = now
    item.gone_at = None
    item.fetch_failure_count = 0
    item.last_error_message = None

    content_hash = detail.content_hash()
    if content_hash != item.content_hash:
        item.versions.append(
            MarketplaceItemVersion(
                fetched_at=now,
                content_hash=content_hash,
                snapshot_json=json.dumps(detail.snapshot(), ensure_ascii=False),
            )
        )
        item.content_hash = content_hash
    db_session.flush()


def _record_fetch_failure(
    item: MarketplaceItem, message: str, now: datetime, settings: Settings
) -> None:
    item.fetch_failure_count += 1
    item.last_error_message = message[:512]
    if item.fetch_failure_count >= MAX_FETCH_FAILURES:
        if item.archived_at is None:
            item.status = "error"
        item.next_fetch_at = now + timedelta(days=max(1, settings.marketplace_archive_refresh_days))
    else:
        item.next_fetch_at = now + timedelta(seconds=_backoff_seconds(item.fetch_failure_count, settings))
    metrics.inc("marketplace.archive_failed")
    logger.warning(
        "marketplace_archive.failed item_id=%s failures=%s reason=%s",
        item.item_id,
        item.fetch_failure_count,
        message,
    )


def _is_blocked(marketplace: str, now: datetime) -> bool:
    until = _block_state.get(marketplace, {}).get("until")
    return until is not None and now < until


def _record_block(marketplace: str, message: str, settings: Settings) -> None:
    state = _block_state.setdefault(marketplace, {"until": None, "count": 0})
    state["count"] += 1
    seconds = _backoff_seconds(state["count"], settings)
    state["until"] = datetime.now(UTC) + timedelta(seconds=seconds)
    metrics.inc("marketplace.archive_blocked")
    logger.warning(
        "marketplace_archive.blocked platform=%s pause_seconds=%s blocks=%s reason=%s",
        marketplace,
        seconds,
        state["count"],
        message,
    )


def reset_block_state() -> None:
    _block_state.clear()


def _backoff_seconds(attempt: int, settings: Settings) -> int:
    backoff = max(1, settings.retry_interval_seconds) * (
        max(1, settings.retry_backoff_multiplier) ** max(attempt - 1, 0)
    )
    return min(backoff, max(1, settings.retry_max_interval_seconds))


# --- Queries used by the API --------------------------------------------------


def list_archive_items(
    db_session: Session,
    *,
    owner_id: str,
    q: str | None = None,
    search_id: int | None = None,
    status: str | None = None,
    marketplace: str | None = None,
    sort: str = "first_seen",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MarketplaceItem], int]:
    conditions = [MarketplaceItem.owner_id == owner_id]
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        conditions.append(
            or_(
                MarketplaceItem.title.ilike(pattern),
                MarketplaceItem.description_text.ilike(pattern),
            )
        )
    if search_id is not None:
        conditions.append(
            MarketplaceItem.item_id.in_(
                select(MarketplaceListing.item_id)
                .join(MarketplaceSearch, MarketplaceSearch.id == MarketplaceListing.search_id)
                .where(
                    MarketplaceSearch.id == search_id,
                    MarketplaceSearch.owner_id == owner_id,
                )
            )
        )
    if marketplace is not None:
        conditions.append(MarketplaceItem.marketplace == marketplace)
    if status == "online":
        conditions.append(MarketplaceItem.gone_at.is_(None))
    elif status == "gone":
        conditions.append(MarketplaceItem.gone_at.is_not(None))

    column = {
        "first_seen": MarketplaceItem.first_seen_at,
        "last_seen": MarketplaceItem.last_seen_at,
        "price": MarketplaceItem.price,
        "title": func.lower(MarketplaceItem.title),
    }.get(sort, MarketplaceItem.first_seen_at)
    ordering = column.asc() if order == "asc" else column.desc()

    total = db_session.scalar(
        select(func.count()).select_from(MarketplaceItem).where(*conditions)
    )
    items = db_session.scalars(
        select(MarketplaceItem)
        .where(*conditions)
        .order_by(column.is_(None), ordering, MarketplaceItem.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), int(total or 0)


def get_archive_item(
    db_session: Session, *, owner_id: str, archive_id: int
) -> MarketplaceItem | None:
    return db_session.scalar(
        select(MarketplaceItem).where(
            MarketplaceItem.id == archive_id, MarketplaceItem.owner_id == owner_id
        )
    )


def get_archive_image(db_session: Session, image_id: int) -> MarketplaceItemImage | None:
    return db_session.get(MarketplaceItemImage, image_id)


def archive_ids_for(db_session: Session, *, owner_id: str, item_ids: list[str]) -> dict[str, int]:
    if not item_ids:
        return {}
    rows = db_session.execute(
        select(MarketplaceItem.item_id, MarketplaceItem.id).where(
            MarketplaceItem.owner_id == owner_id,
            MarketplaceItem.item_id.in_(item_ids),
        )
    ).all()
    return {row.item_id: row.id for row in rows}


def item_searches(
    db_session: Session, *, owner_id: str, item_ids: list[str]
) -> dict[str, list[tuple[int, str]]]:
    if not item_ids:
        return {}
    rows = db_session.execute(
        select(MarketplaceListing.item_id, MarketplaceSearch.id, MarketplaceSearch.name)
        .join(MarketplaceSearch, MarketplaceSearch.id == MarketplaceListing.search_id)
        .where(
            MarketplaceSearch.owner_id == owner_id,
            MarketplaceListing.item_id.in_(item_ids),
        )
        .order_by(MarketplaceSearch.name)
    ).all()
    result: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        result.setdefault(row.item_id, []).append((row.id, row.name))
    return result


def duplicate_items(db_session: Session, item: MarketplaceItem) -> list[MarketplaceItem]:
    """Other archived listings of the same car (same license plate), e.g. on another platform."""
    if not item.license_plate:
        return []
    return list(
        db_session.scalars(
            select(MarketplaceItem)
            .where(
                MarketplaceItem.owner_id == item.owner_id,
                MarketplaceItem.license_plate == item.license_plate,
                MarketplaceItem.id != item.id,
            )
            .order_by(MarketplaceItem.gone_at.is_not(None), MarketplaceItem.first_seen_at.desc())
        ).all()
    )


def plate_from_attributes(groups: list[dict[str, Any]]) -> str | None:
    for group in groups:
        for attribute in group.get("items") or []:
            if attribute.get("key") == "licensePlate":
                return normalize_plate(attribute.get("value"))
    return None


def cover_images(db_session: Session, archive_ids: list[int]) -> dict[int, int]:
    """First current photo per archive item."""
    if not archive_ids:
        return {}
    rows = db_session.execute(
        select(MarketplaceItemImage.item_id, MarketplaceItemImage.id)
        .where(
            MarketplaceItemImage.item_id.in_(archive_ids),
            MarketplaceItemImage.removed_at.is_(None),
        )
        .order_by(MarketplaceItemImage.item_id, MarketplaceItemImage.position)
    ).all()
    result: dict[int, int] = {}
    for row in rows:
        result.setdefault(row.item_id, row.id)
    return result


def archive_usage(db_session: Session, *, owner_id: str) -> ArchiveUsage:
    items = db_session.scalar(
        select(func.count()).select_from(MarketplaceItem).where(
            MarketplaceItem.owner_id == owner_id
        )
    )
    files = (
        select(MarketplaceItemImage.file_path, MarketplaceItemImage.size_bytes)
        .join(MarketplaceItem, MarketplaceItem.id == MarketplaceItemImage.item_id)
        .where(MarketplaceItem.owner_id == owner_id)
        .distinct()
        .subquery()
    )
    images, size = db_session.execute(
        select(func.count(), func.coalesce(func.sum(files.c.size_bytes), 0))
    ).one()
    return ArchiveUsage(items=int(items or 0), images=int(images or 0), bytes=int(size or 0))


def delete_archive_item(db_session: Session, item: MarketplaceItem, store: ArchiveStore) -> None:
    marketplace, item_id = item.marketplace, item.item_id
    # Photos may sit under another platform's folder (adopted items).
    folders = {tuple(image.file_path.split("/")[:2]) for image in item.images}
    db_session.delete(item)
    db_session.commit()
    store.delete_item(marketplace, item_id)
    for folder_marketplace, folder_item in folders:
        if folder_item == item_id:
            store.delete_item(folder_marketplace, folder_item)
    logger.info("marketplace_archive.deleted item_id=%s", item_id)


def refresh_archive_item(db_session: Session, item: MarketplaceItem) -> MarketplaceItem:
    item.next_fetch_at = datetime.now(UTC)
    item.fetch_failure_count = 0
    db_session.commit()
    db_session.refresh(item)
    return item


def version_changes(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    """Differences between two version snapshots, for display."""
    if previous is None:
        return {"fields": [], "description_diff": [], "images_added": 0, "images_removed": 0}

    fields: list[dict[str, str | None]] = []

    def compare(label: str, before: Any, after: Any) -> None:
        if before != after:
            fields.append(
                {"label": label, "before": _display(before), "after": _display(after)}
            )

    compare("Title", previous.get("title"), current.get("title"))
    compare("Price", _price_label(previous), _price_label(current))
    compare("Location", previous.get("city"), current.get("city"))
    compare("Reserved", previous.get("is_reserved"), current.get("is_reserved"))
    compare(
        "Seller",
        (previous.get("seller") or {}).get("name"),
        (current.get("seller") or {}).get("name"),
    )
    compare("Highlights", previous.get("highlights"), current.get("highlights"))

    before_attributes = _flatten_attributes(previous.get("attribute_groups"))
    after_attributes = _flatten_attributes(current.get("attribute_groups"))
    for label in [*after_attributes, *[key for key in before_attributes if key not in after_attributes]]:
        compare(label, before_attributes.get(label), after_attributes.get(label))

    before_text = (previous.get("description_text") or "").splitlines()
    after_text = (current.get("description_text") or "").splitlines()
    diff = [
        line
        for line in difflib.unified_diff(before_text, after_text, lineterm="", n=0)
        if not line.startswith(("---", "+++", "@@"))
    ]

    before_images = {image.get("key") for image in previous.get("images") or []}
    after_images = {image.get("key") for image in current.get("images") or []}
    return {
        "fields": fields,
        "description_diff": diff,
        "images_added": len(after_images - before_images),
        "images_removed": len(before_images - after_images),
    }


def _flatten_attributes(groups: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for group in groups or []:
        for item in group.get("items") or []:
            label = item.get("label")
            if label and label not in result:
                result[label] = str(item.get("value"))
    return result


def _price_label(snapshot: dict[str, Any]) -> str | None:
    price = snapshot.get("price")
    if price is None:
        return snapshot.get("price_type")
    whole = Decimal(price).quantize(Decimal("1"))
    return f"€ {int(whole):,}".replace(",", ".")


def _display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _items_by_key(
    db_session: Session, keys: list[tuple[str, str]]
) -> dict[tuple[str, str], MarketplaceItem]:
    wanted = set(keys)
    items = db_session.scalars(
        select(MarketplaceItem).where(MarketplaceItem.item_id.in_({item_id for _, item_id in keys}))
    ).all()
    return {
        (item.marketplace, item.item_id): item
        for item in items
        if (item.marketplace, item.item_id) in wanted
    }


def _adopt_shared_item(db_session: Session, listing: Listing) -> MarketplaceItem | None:
    """Move an archive item of a platform with the same listing ids (AutoTrack →
    AutoScout24) to ``listing``'s platform, keeping its versions and photos."""
    other = SHARED_LISTING_IDS.get(listing.marketplace)
    if other is None:
        return None
    item = db_session.scalar(
        select(MarketplaceItem).where(
            MarketplaceItem.marketplace == other, MarketplaceItem.item_id == listing.item_id
        )
    )
    if item is not None:
        item.marketplace = listing.marketplace
        item.url = listing.url
        item.next_fetch_at = item.next_fetch_at or datetime.now(UTC)
        logger.info(
            "marketplace_archive.adopted item_id=%s from=%s to=%s",
            item.item_id,
            other,
            listing.marketplace,
        )
    return item


def _backfill_license_plates(db_session: Session) -> None:
    """Plates of items archived before plates were stored (Marktplaats car attributes)."""
    for item in db_session.scalars(
        select(MarketplaceItem).where(
            MarketplaceItem.license_plate.is_(None),
            MarketplaceItem.attribute_groups_json.contains('"licensePlate"'),
        )
    ).all():
        item.license_plate = plate_from_attributes(json.loads(item.attribute_groups_json))
    db_session.flush()


def _new_item(
    owner_id: str, marketplace: str, item_id: str, url: str, title: str, now: datetime
) -> MarketplaceItem:
    return MarketplaceItem(
        owner_id=owner_id,
        marketplace=marketplace,
        item_id=item_id,
        url=url,
        title=title[:512],
        listing_title=title[:512],
        status="pending",
        first_seen_at=now,
        last_seen_at=now,
        next_fetch_at=now,
        fetch_failure_count=0,
        category_json="[]",
        summary_attributes_json="{}",
        attribute_groups_json="[]",
        seller_json="{}",
        stats_json="{}",
        highlights_json="[]",
        is_reserved=False,
    )


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _safe_segment(value: str) -> str:
    if not _SAFE_SEGMENT.match(value):
        raise ValueError(f"Unexpected path segment: {value!r}")
    return value
