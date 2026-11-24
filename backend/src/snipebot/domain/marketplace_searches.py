"""Saved marketplace searches: detect new listings and price drops.

Each check fetches the newest listings for a saved Marktplaats search. The
first successful check records the current listings silently (baseline).
Later checks notify for listings that are genuinely new and for price drops on
known listings.

Marktplaats re-lists paid "Dagtopper" ads at the top every day, so an unseen
listing is not necessarily a new one. Listing ids increase over time: an unseen
listing counts as new when its id is above the highest id known for the search,
or when the previous check covered the complete result set (then any unseen
listing has just entered the search, e.g. after a price cut).
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces.marktplaats import (
    SELLER_TYPES,
    Listing,
    MarktplaatsClient,
    MarktplaatsError,
    SearchQuery,
    apply_seller_type,
    describe_query,
)
from snipebot.core.config import Settings
from snipebot.core.metrics import metrics
from snipebot.domain.price_checks import resolve_notification_settings
from snipebot.notifications.factory import build_notifier
from snipebot.notifications.models import NotificationMessage
from snipebot.persistence.models import (
    MarketplaceAlertEvent,
    MarketplaceListing,
    MarketplaceListingPrice,
    MarketplaceSearch,
)

logger = logging.getLogger(__name__)

MAX_KEYWORDS = 50
MAX_ALERTS_PER_CHECK = 10
NEW_LISTING_WINDOW = timedelta(hours=48)
DUE_BATCH_SIZE = 10

_SELLER_LABELS = {"private": "Particulier", "business": "Bedrijf"}
_PRICE_TYPE_LABELS = {
    "MIN_BID": "bieden vanaf",
    "FAST_BID": "bieden",
    "BID": "bieden",
    "SEE_DESCRIPTION": "zie omschrijving",
    "NOTK": "n.o.t.k.",
    "EXCHANGE": "ruilen",
    "FREE": "gratis",
    "RESERVED": "gereserveerd",
    "ON_REQUEST": "op aanvraag",
}


@dataclass(slots=True)
class SearchPreview:
    query: SearchQuery
    description: list[str]
    warnings: list[str]
    total_count: int
    sample: list[Listing]


@dataclass(slots=True)
class _AlertIntent:
    kind: str
    row: MarketplaceListing
    listing: Listing
    old_price: Decimal | None = None

    @property
    def dedup_key(self) -> str:
        if self.kind == "price_drop":
            return f"price_drop|old={self.old_price:.2f}|new={self.listing.price:.2f}"
        return "new_listing"


# --- Service functions used by the API -------------------------------------


def normalize_keywords(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        keyword = " ".join(value.split()).lower()
        if keyword and keyword not in result:
            result.append(keyword[:100])
    if len(result) > MAX_KEYWORDS:
        raise ValueError(f"At most {MAX_KEYWORDS} exclude keywords are allowed")
    return result


def preview_search(
    client: MarktplaatsClient, *, url: str, seller_type: str = "all"
) -> SearchPreview:
    if seller_type not in SELLER_TYPES:
        raise ValueError(f"Unknown seller type: {seller_type}")
    resolved = client.resolve(url)
    page = client.search(resolved.query, limit=5)
    query = apply_seller_type(resolved.query, seller_type, page.facets)
    if query.attribute_ids != resolved.query.attribute_ids:
        page = client.search(query, limit=5)
    return SearchPreview(
        query=query,
        description=describe_query(query, page.facets, resolved.category_names),
        warnings=resolved.warnings,
        total_count=page.total_count,
        sample=page.listings[:5],
    )


def create_search(
    db_session: Session,
    client: MarktplaatsClient,
    *,
    owner_id: str,
    name: str,
    url: str,
    exclude_keywords: list[str] | None,
    seller_type: str,
) -> MarketplaceSearch:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Name is required")
    keywords = normalize_keywords(exclude_keywords)
    preview = preview_search(client, url=url, seller_type=seller_type)

    search = MarketplaceSearch(
        owner_id=owner_id,
        marketplace="marktplaats",
        name=clean_name[:255],
        source_url=url.strip(),
        query_json=json.dumps(preview.query.to_dict()),
        description_json=json.dumps(preview.description),
        exclude_keywords_json=json.dumps(keywords),
        seller_type=seller_type,
        active=True,
        baseline_done=False,
        last_status="pending",
        next_check_at=datetime.now(UTC),
    )
    db_session.add(search)
    db_session.commit()
    db_session.refresh(search)
    logger.info(
        "marketplace_search.created search_id=%s owner_id=%s total=%s",
        search.id,
        owner_id,
        preview.total_count,
    )
    return search


def update_search(
    db_session: Session,
    client: MarktplaatsClient,
    search: MarketplaceSearch,
    *,
    name: str | None = None,
    exclude_keywords: list[str] | None = None,
    seller_type: str | None = None,
    active: bool | None = None,
) -> MarketplaceSearch:
    filters_changed = False

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Name is required")
        search.name = clean_name[:255]

    if exclude_keywords is not None:
        keywords = normalize_keywords(exclude_keywords)
        if keywords != get_exclude_keywords(search):
            search.exclude_keywords_json = json.dumps(keywords)
            filters_changed = True

    if seller_type is not None and seller_type != search.seller_type:
        if seller_type not in SELLER_TYPES:
            raise ValueError(f"Unknown seller type: {seller_type}")
        preview = preview_search(client, url=search.source_url, seller_type=seller_type)
        search.query_json = json.dumps(preview.query.to_dict())
        search.description_json = json.dumps(preview.description)
        search.seller_type = seller_type
        filters_changed = True

    if active is not None and active != search.active:
        search.active = active
        if active:
            search.next_check_at = datetime.now(UTC)
            search.consecutive_failure_count = 0

    if filters_changed:
        # Changed filters change the result set; record it silently again so
        # listings that now match are not reported as new.
        search.baseline_done = False
        search.next_check_at = datetime.now(UTC)

    db_session.commit()
    db_session.refresh(search)
    return search


def get_search(
    db_session: Session, *, owner_id: str, search_id: int
) -> MarketplaceSearch | None:
    return db_session.scalar(
        select(MarketplaceSearch).where(
            MarketplaceSearch.id == search_id, MarketplaceSearch.owner_id == owner_id
        )
    )


def list_searches(db_session: Session, *, owner_id: str) -> list[MarketplaceSearch]:
    return list(
        db_session.scalars(
            select(MarketplaceSearch)
            .where(MarketplaceSearch.owner_id == owner_id)
            .order_by(MarketplaceSearch.created_at.desc(), MarketplaceSearch.id.desc())
        ).all()
    )


def delete_search(db_session: Session, search: MarketplaceSearch) -> None:
    db_session.delete(search)
    db_session.commit()


def trigger_search_check_now(
    db_session: Session, search: MarketplaceSearch
) -> MarketplaceSearch:
    search.next_check_at = datetime.now(UTC)
    db_session.commit()
    db_session.refresh(search)
    return search


def list_search_listings(
    db_session: Session, search: MarketplaceSearch
) -> list[MarketplaceListing]:
    return list(
        db_session.scalars(
            select(MarketplaceListing)
            .where(MarketplaceListing.search_id == search.id)
            .order_by(
                MarketplaceListing.gone_at.is_not(None),
                MarketplaceListing.first_seen_at.desc(),
                MarketplaceListing.id.desc(),
            )
        ).all()
    )


def search_listing_counts(db_session: Session, search: MarketplaceSearch) -> tuple[int, int]:
    """Return (visible listings, new listings) for overview display."""
    rows = db_session.execute(
        select(
            MarketplaceListing.from_baseline,
            MarketplaceListing.first_seen_at,
            MarketplaceListing.gone_at,
        ).where(MarketplaceListing.search_id == search.id)
    ).all()
    now = datetime.now(UTC)
    visible = sum(1 for row in rows if row.gone_at is None)
    new = sum(
        1
        for row in rows
        if row.gone_at is None and _is_new(row.from_baseline, row.first_seen_at, now)
    )
    return visible, new


def is_listing_new(listing: MarketplaceListing, now: datetime | None = None) -> bool:
    return _is_new(listing.from_baseline, listing.first_seen_at, now or datetime.now(UTC))


def get_search_query(search: MarketplaceSearch) -> SearchQuery:
    return SearchQuery.from_dict(json.loads(search.query_json))


def get_search_description(search: MarketplaceSearch) -> list[str]:
    return list(json.loads(search.description_json or "[]"))


def get_exclude_keywords(search: MarketplaceSearch) -> list[str]:
    return list(json.loads(search.exclude_keywords_json or "[]"))


# --- Worker ------------------------------------------------------------------


def run_due_marketplace_searches(
    db_session: Session,
    settings: Settings,
    *,
    client: MarktplaatsClient | None = None,
    notifier=None,
) -> int:
    now = datetime.now(UTC)
    searches = list(
        db_session.scalars(
            select(MarketplaceSearch)
            .where(
                MarketplaceSearch.active.is_(True),
                or_(
                    MarketplaceSearch.next_check_at.is_(None),
                    MarketplaceSearch.next_check_at <= now,
                ),
            )
            .order_by(MarketplaceSearch.next_check_at.asc().nullsfirst())
            .limit(DUE_BATCH_SIZE)
        ).all()
    )
    if not searches:
        return 0

    (
        notifications_enabled,
        telegram_enabled,
        telegram_bot_token,
        telegram_chat_id,
    ) = resolve_notification_settings(db_session, settings)
    alerts_enabled = notifications_enabled and telegram_enabled
    if notifier is None:
        notifier = build_notifier(
            settings,
            notifications_enabled=notifications_enabled,
            telegram_enabled=telegram_enabled,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
        )
    client = client or MarktplaatsClient()

    processed = 0
    for search in searches:
        processed += 1
        search_id = search.id
        try:
            check_search(
                db_session,
                search,
                settings,
                client=client,
                notifier=notifier,
                alerts_enabled=alerts_enabled,
            )
            db_session.commit()
        except Exception as exc:  # pragma: no cover - safety net
            db_session.rollback()
            metrics.inc("marketplace.search_unhandled_error")
            logger.exception(
                "marketplace_search.unhandled_error search_id=%s reason=%s",
                search_id,
                exc,
            )
            failed = db_session.get(MarketplaceSearch, search_id)
            if failed is not None:
                _record_failure(failed, "error", str(exc), datetime.now(UTC), settings)
                db_session.commit()
    return processed


def check_search(
    db_session: Session,
    search: MarketplaceSearch,
    settings: Settings,
    *,
    client: MarktplaatsClient,
    notifier,
    alerts_enabled: bool,
) -> None:
    now = datetime.now(UTC)
    search.last_checked_at = now
    search.check_count += 1

    try:
        page = client.search(get_search_query(search))
    except MarktplaatsError as exc:
        _record_failure(search, exc.kind, str(exc), now, settings)
        return

    baseline = not search.baseline_done
    previous_full_coverage = (
        search.last_total_count is not None
        and search.last_fetched_count is not None
        and search.last_total_count <= search.last_fetched_count
    )
    watermark = search.id_watermark
    keywords = get_exclude_keywords(search)

    page_ids = {listing.item_id for listing in page.listings}
    matching = [listing for listing in page.listings if not _is_excluded(listing, keywords)]
    known = {
        row.item_id: row
        for row in db_session.scalars(
            select(MarketplaceListing).where(
                MarketplaceListing.search_id == search.id,
                MarketplaceListing.item_id.in_([listing.item_id for listing in matching]),
            )
        ).all()
    }

    intents: list[_AlertIntent] = []
    for listing in matching:
        row = known.get(listing.item_id)
        if row is None:
            row = _create_listing_row(db_session, search, listing, now, baseline)
            if baseline:
                continue
            if _counts_as_new(listing, watermark, previous_full_coverage):
                intents.append(_AlertIntent(kind="new_listing", row=row, listing=listing))
            else:
                logger.info(
                    "marketplace_search.older_listing search_id=%s item_id=%s",
                    search.id,
                    listing.item_id,
                )
            continue

        old_price = row.current_price
        _update_listing_row(row, listing, now)
        if (
            listing.price is not None
            and old_price is not None
            and listing.price < old_price
        ):
            intents.append(
                _AlertIntent(kind="price_drop", row=row, listing=listing, old_price=old_price)
            )

    if page.total_count <= len(page.listings):
        # The page holds the complete result set, so anything missing is gone.
        for row in db_session.scalars(
            select(MarketplaceListing).where(
                MarketplaceListing.search_id == search.id,
                MarketplaceListing.gone_at.is_(None),
            )
        ).all():
            if row.item_id not in page_ids:
                row.gone_at = now

    ids = [value for listing in page.listings if (value := listing.numeric_id) is not None]
    if ids:
        search.id_watermark = max([*ids, watermark or 0])
    search.baseline_done = True
    search.last_total_count = page.total_count
    search.last_fetched_count = len(page.listings)
    search.last_status = "ok"
    search.last_error_message = None
    search.consecutive_failure_count = 0
    jitter = max(0, settings.marketplace_check_jitter_seconds)
    search.next_check_at = now + timedelta(
        seconds=max(60, settings.marketplace_check_interval_seconds)
        + random.randint(-jitter, jitter)
    )
    db_session.flush()

    metrics.inc("marketplace.search_checked")
    logger.info(
        "marketplace_search.ok search_id=%s baseline=%s total=%s fetched=%s matching=%s alerts=%s",
        search.id,
        baseline,
        page.total_count,
        len(page.listings),
        len(matching),
        len(intents),
    )

    if intents and alerts_enabled:
        _dispatch_alerts(db_session, search, intents, notifier, now)


def _counts_as_new(
    listing: Listing, watermark: int | None, previous_full_coverage: bool
) -> bool:
    if previous_full_coverage or watermark is None:
        return True
    numeric_id = listing.numeric_id
    return numeric_id is not None and numeric_id > watermark


def _is_excluded(listing: Listing, keywords: list[str]) -> bool:
    if not keywords:
        return False
    haystack = f"{listing.title}\n{listing.description}".lower()
    return any(keyword in haystack for keyword in keywords)


def _is_new(from_baseline: bool, first_seen_at: datetime, now: datetime) -> bool:
    if from_baseline:
        return False
    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=UTC)
    return now - first_seen_at <= NEW_LISTING_WINDOW


def _create_listing_row(
    db_session: Session,
    search: MarketplaceSearch,
    listing: Listing,
    now: datetime,
    baseline: bool,
) -> MarketplaceListing:
    row = MarketplaceListing(
        search_id=search.id,
        item_id=listing.item_id,
        title=listing.title[:512],
        url=listing.url,
        image_url=listing.image_url,
        price_type=listing.price_type,
        first_price=listing.price,
        current_price=listing.price,
        city=listing.city,
        distance_meters=listing.distance_meters,
        seller_type=listing.seller_type or _seller_from_filter(search),
        attributes_json=json.dumps(listing.attributes, ensure_ascii=False),
        from_baseline=baseline,
        first_seen_at=now,
        last_seen_at=now,
    )
    if listing.price is not None:
        row.prices.append(MarketplaceListingPrice(price=listing.price, observed_at=now))
    db_session.add(row)
    return row


def _update_listing_row(row: MarketplaceListing, listing: Listing, now: datetime) -> None:
    row.title = listing.title[:512]
    row.url = listing.url
    row.image_url = listing.image_url or row.image_url
    row.price_type = listing.price_type
    row.city = listing.city
    row.distance_meters = listing.distance_meters
    row.attributes_json = json.dumps(listing.attributes, ensure_ascii=False)
    row.last_seen_at = now
    row.gone_at = None
    if listing.seller_type:
        row.seller_type = listing.seller_type
    if listing.price is not None and listing.price != row.current_price:
        row.prices.append(MarketplaceListingPrice(price=listing.price, observed_at=now))
        row.current_price = listing.price


def _seller_from_filter(search: MarketplaceSearch) -> str | None:
    return search.seller_type if search.seller_type in _SELLER_LABELS else None


def _record_failure(
    search: MarketplaceSearch,
    kind: str,
    message: str,
    now: datetime,
    settings: Settings,
) -> None:
    search.consecutive_failure_count += 1
    backoff = max(1, settings.retry_interval_seconds) * (
        max(1, settings.retry_backoff_multiplier)
        ** max(search.consecutive_failure_count - 1, 0)
    )
    backoff = min(backoff, max(1, settings.retry_max_interval_seconds))
    search.last_status = kind
    search.last_error_message = message[:512]
    search.next_check_at = now + timedelta(seconds=backoff)
    metrics.inc(f"marketplace.search_failed.{kind}")
    logger.warning(
        "marketplace_search.failed search_id=%s kind=%s failures=%s reason=%s",
        search.id,
        kind,
        search.consecutive_failure_count,
        message,
    )


def _dispatch_alerts(
    db_session: Session,
    search: MarketplaceSearch,
    intents: list[_AlertIntent],
    notifier,
    now: datetime,
) -> None:
    pending: list[_AlertIntent] = []
    for intent in intents:
        already_sent = db_session.scalar(
            select(MarketplaceAlertEvent.id)
            .where(
                MarketplaceAlertEvent.listing_id == intent.row.id,
                MarketplaceAlertEvent.alert_kind == intent.kind,
                MarketplaceAlertEvent.dedup_key == intent.dedup_key,
                MarketplaceAlertEvent.delivery_status == "sent",
            )
            .limit(1)
        )
        if already_sent is None:
            pending.append(intent)

    for intent in pending[:MAX_ALERTS_PER_CHECK]:
        message = format_listing_message(search, intent.kind, intent.listing, intent.old_price)
        result = notifier.send(message)
        if not result.ok and result.error == "notifications_disabled":
            continue
        status = "sent" if result.ok else "failed"
        db_session.add(
            MarketplaceAlertEvent(
                search_id=search.id,
                listing_id=intent.row.id,
                alert_kind=intent.kind,
                dedup_key=intent.dedup_key,
                channel="telegram",
                delivery_status=status,
                sent_at=now,
                provider_message_id=result.provider_message_id,
                message_text=message.text,
                error_message=None if result.ok else result.error,
            )
        )
        metrics.inc(f"marketplace.alert.{status}")
        log = logger.info if result.ok else logger.warning
        log(
            "marketplace_alert.%s search_id=%s item_id=%s kind=%s reason=%s",
            status,
            search.id,
            intent.listing.item_id,
            intent.kind,
            result.error,
        )

    overflow = len(pending) - MAX_ALERTS_PER_CHECK
    if overflow > 0:
        # Guard against floods (e.g. after a Marktplaats change); the listings
        # are recorded and visible in the UI.
        notifier.send(
            NotificationMessage(
                title=f"🔔 {search.name}",
                body=f"+{overflow} meer nieuwe meldingen; bekijk ze in SnipeBot.",
            )
        )
        logger.warning(
            "marketplace_alert.overflow search_id=%s suppressed=%s", search.id, overflow
        )


def format_listing_message(
    search: MarketplaceSearch,
    kind: str,
    listing: Listing,
    old_price: Decimal | None = None,
) -> NotificationMessage:
    if kind == "price_drop" and old_price is not None and listing.price is not None:
        title = f"📉 Prijsdaling — {search.name}"
        price_line = (
            f"💶 {format_euro(old_price)} → {format_euro(listing.price)}"
            f" (−{format_euro(old_price - listing.price)})"
        )
    else:
        title = f"🆕 Nieuwe advertentie — {search.name}"
        price_line = f"💶 {_format_listing_price(listing)}"

    lines = [listing.title, price_line]
    details = _car_details(listing.attributes)
    if details:
        lines.append(f"🚗 {details}")
    place = _place_line(listing, search)
    if place:
        lines.append(f"📍 {place}")
    lines.append(listing.url)
    return NotificationMessage(
        title=title, body="\n".join(lines), photo_url=listing.image_url
    )


def format_euro(value: Decimal) -> str:
    whole = int(value)
    cents = int((value - whole) * 100)
    text = f"€ {whole:,}".replace(",", ".")
    return f"{text},{cents:02d}" if cents else text


def _format_listing_price(listing: Listing) -> str:
    label = _PRICE_TYPE_LABELS.get(listing.price_type or "")
    if listing.price is None:
        return (label or "prijs onbekend").capitalize()
    price = format_euro(listing.price)
    return f"{price} ({label})" if label else price


def _car_details(attributes: dict[str, str]) -> str:
    parts: list[str] = []
    if attributes.get("constructionYear"):
        parts.append(attributes["constructionYear"])
    mileage = attributes.get("mileage")
    if mileage and mileage.isdigit():
        parts.append(f"{int(mileage):,} km".replace(",", "."))
    for key in ("fuel", "transmission"):
        if attributes.get(key):
            parts.append(attributes[key])
    return " · ".join(parts)


def _place_line(listing: Listing, search: MarketplaceSearch) -> str:
    parts: list[str] = []
    if listing.city:
        if listing.distance_meters is not None:
            parts.append(f"{listing.city} ({round(listing.distance_meters / 1000)} km)")
        else:
            parts.append(listing.city)
    seller = _SELLER_LABELS.get(listing.seller_type or _seller_from_filter(search) or "")
    if seller:
        parts.append(seller)
    return " · ".join(parts)
