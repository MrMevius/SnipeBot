"""Saved marketplace searches: detect new listings and price drops.

A search holds SnipeBot's own filters (make, model, ranges) and searches one or
more platforms; each platform is a ``MarketplaceSearchSource`` with its own
query and check state. Searches created from a pasted Marktplaats URL have no
filters and a single Marktplaats source with the resolved query.

Each check fetches the newest listings of one source. The first successful
check records the current listings silently (baseline). Later checks notify
for listings that are genuinely new and for price drops on known listings.

Filters a platform cannot apply are checked against the listing data. A listing
that does not state the value is handled by the search's ``unknown_policy``:
kept and alerted ("include"), kept without alerts ("quiet") or left out
("exclude").

Telegram alerts are limited by the search's price ceiling (``alert_max_price``):
new listings and price drops alert only when the price is at or below it, and a
search without a ceiling sends no alerts. All listings are still recorded.

Marktplaats re-lists paid "Dagtopper" ads at the top every day, so an unseen
listing is not necessarily a new one. Listing ids increase over time: an unseen
listing counts as new when its id is above the highest id known for the source,
or when the previous check covered the complete result set (then any unseen
listing has just entered the search, e.g. after a price cut).
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces.base import (
    Listing,
    MarketplaceError,
    PlatformAdapter,
    PlatformQuery,
    SearchFilters,
    find_option,
    normalize_label,
)
from snipebot.adapters.marketplaces.marktplaats import SELLER_TYPES
from snipebot.adapters.marketplaces.platforms import (
    PLATFORM_LABELS,
    SHARED_LISTING_IDS,
    get_adapters,
    home_location,
    platform_label,
)
from snipebot.core.config import Settings
from snipebot.core.metrics import metrics
from snipebot.domain.marketplace_archive import (
    ARCHIVE_MARKETPLACES,
    mark_listings_missing,
    observe_listings,
)
from snipebot.domain.price_checks import resolve_notification_settings
from snipebot.domain.search_filters import (
    FILTER_LABELS,
    check_listing,
    describe_filters,
    validate_filters,
)
from snipebot.notifications.factory import build_notifier
from snipebot.notifications.models import NotificationMessage
from snipebot.persistence.models import (
    MarketplaceAlertEvent,
    MarketplaceListing,
    MarketplaceListingPrice,
    MarketplaceSearch,
    MarketplaceSearchSource,
)

logger = logging.getLogger(__name__)

Adapters = dict[str, PlatformAdapter]

MAX_KEYWORDS = 50
_UNSET = object()
MAX_ALERTS_PER_CHECK = 10
NEW_LISTING_WINDOW = timedelta(hours=48)
DUE_BATCH_SIZE = 10
UNKNOWN_POLICIES = ("include", "quiet", "exclude")
PREVIEW_SAMPLE_SIZE = 5

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
class MergedOption:
    """A make or model, with the platforms that know it."""

    label: str
    platforms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlatformPreview:
    marketplace: str
    total_count: int | None
    sample: list[Listing]
    post_filters: list[str]
    error: str | None = None


@dataclass(slots=True)
class SearchPreview:
    description: list[str]
    platforms: list[PlatformPreview]


@dataclass(slots=True)
class SearchStatus:
    """Check state of a search, combined over its sources."""

    baseline_done: bool
    last_checked_at: datetime | None
    next_check_at: datetime | None
    last_status: str
    last_error_message: str | None
    last_total_count: int | None


@dataclass(slots=True)
class _AlertIntent:
    kind: str
    row: MarketplaceListing
    listing: Listing
    old_price: Decimal | None = None
    unknown_filters: list[str] = field(default_factory=list)

    @property
    def dedup_key(self) -> str:
        if self.kind == "price_drop":
            return f"price_drop|old={self.old_price:.2f}|new={self.listing.price:.2f}"
        return "new_listing"


# --- Makes and models --------------------------------------------------------


def list_makes(adapters: Adapters) -> tuple[list[MergedOption], list[str]]:
    """Makes of all platforms merged by name; warnings name unreachable platforms."""
    merged: dict[str, MergedOption] = {}
    warnings: list[str] = []
    for key, adapter in _ordered(adapters):
        try:
            options = adapter.makes()
        except MarketplaceError as exc:
            warnings.append(f"{adapter.label}: {exc}")
            continue
        for option in options:
            _merge(merged, option.label, key)
    return sorted(merged.values(), key=lambda option: option.label.lower()), warnings


def list_models(adapters: Adapters, make: str) -> tuple[list[MergedOption], list[str]]:
    merged: dict[str, MergedOption] = {}
    warnings: list[str] = []
    for key, adapter in _ordered(adapters):
        try:
            make_option = find_option(adapter.makes(), make)
            options = adapter.models(make_option) if make_option is not None else []
        except MarketplaceError as exc:
            warnings.append(f"{adapter.label}: {exc}")
            continue
        for option in options:
            _merge(merged, option.label, key)
    return sorted(merged.values(), key=lambda option: option.label.lower()), warnings


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
    adapters: Adapters,
    *,
    filters: SearchFilters,
    platforms: list[str],
    seller_type: str = "all",
    exclude_keywords: list[str] | None = None,
) -> SearchPreview:
    filters = validate_filters(filters)
    platforms = _validate_platforms(adapters, platforms)
    _validate_seller_type(seller_type)
    keywords = normalize_keywords(exclude_keywords)
    results: list[PlatformPreview] = []
    for key in platforms:
        adapter = adapters[key]
        try:
            built = adapter.build_query(filters, seller_type)
            page = adapter.search(built.query, limit=20)
        except MarketplaceError as exc:
            results.append(PlatformPreview(key, None, [], [], str(exc)))
            continue
        sample = [
            listing
            for listing in page.listings
            if not _is_excluded(listing, keywords)
            and check_listing(filters, listing, built.post_filters)[0]
        ]
        results.append(
            PlatformPreview(
                key, page.total_count, sample[:PREVIEW_SAMPLE_SIZE], built.post_filters
            )
        )
    return SearchPreview(description=describe_filters(filters, seller_type), platforms=results)


def create_search(
    db_session: Session,
    adapters: Adapters,
    *,
    owner_id: str,
    name: str,
    filters: SearchFilters,
    platforms: list[str],
    exclude_keywords: list[str] | None,
    seller_type: str,
    alert_max_price: Decimal | None = None,
    unknown_policy: str = "include",
) -> MarketplaceSearch:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Name is required")
    filters = validate_filters(filters)
    platforms = _validate_platforms(adapters, platforms)
    _validate_seller_type(seller_type)
    _validate_unknown_policy(unknown_policy)
    keywords = normalize_keywords(exclude_keywords)
    queries = _build_queries(adapters, filters, platforms, seller_type)

    now = datetime.now(UTC)
    search = MarketplaceSearch(
        owner_id=owner_id,
        marketplace=platforms[0],
        name=clean_name[:255],
        source_url="",
        query_json="{}",
        filters_json=json.dumps(filters.to_dict()),
        description_json=json.dumps(describe_filters(filters, seller_type)),
        exclude_keywords_json=json.dumps(keywords),
        seller_type=seller_type,
        alert_max_price=_validate_ceiling(alert_max_price),
        unknown_policy=unknown_policy,
        active=True,
        baseline_done=False,
        last_status="pending",
    )
    for key, built in queries.items():
        search.sources.append(_new_source(key, built, now))
    db_session.add(search)
    db_session.commit()
    db_session.refresh(search)
    logger.info(
        "marketplace_search.created search_id=%s owner_id=%s platforms=%s",
        search.id,
        owner_id,
        ",".join(platforms),
    )
    return search


def update_search(
    db_session: Session,
    adapters: Adapters,
    search: MarketplaceSearch,
    *,
    name: str | None = None,
    exclude_keywords: list[str] | None = None,
    seller_type: str | None = None,
    active: bool | None = None,
    alert_max_price: Decimal | None | object = _UNSET,
    filters: SearchFilters | None = None,
    platforms: list[str] | None = None,
    unknown_policy: str | None = None,
) -> MarketplaceSearch:
    now = datetime.now(UTC)

    if unknown_policy is not None and unknown_policy != search.unknown_policy:
        _validate_unknown_policy(unknown_policy)
        previous, search.unknown_policy = search.unknown_policy, unknown_policy
        if previous == "exclude":
            # Listings left out so far would otherwise show up as new.
            for source in search.sources:
                if get_post_filters(source):
                    _restart_baseline(source, now)

    if alert_max_price is not _UNSET:
        # Only affects which future events alert; no new baseline needed.
        search.alert_max_price = _validate_ceiling(alert_max_price)

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Name is required")
        search.name = clean_name[:255]

    keywords_changed = False
    if exclude_keywords is not None:
        keywords = normalize_keywords(exclude_keywords)
        if keywords != get_exclude_keywords(search):
            search.exclude_keywords_json = json.dumps(keywords)
            keywords_changed = True

    seller_changed = seller_type is not None and seller_type != search.seller_type
    if seller_changed:
        _validate_seller_type(seller_type)
    if filters is not None or platforms is not None or seller_changed:
        current = get_search_filters(search)
        if filters is None and current is None:
            raise ValueError("Choose a make and a model to change this search")
        new_filters = validate_filters(filters) if filters is not None else current
        new_platforms = _validate_platforms(
            adapters,
            platforms if platforms is not None else [s.marketplace for s in search.sources],
        )
        new_seller = seller_type if seller_type is not None else search.seller_type
        queries = _build_queries(adapters, new_filters, new_platforms, new_seller)
        _sync_sources(db_session, search, queries, now)
        search.filters_json = json.dumps(new_filters.to_dict())
        search.description_json = json.dumps(describe_filters(new_filters, new_seller))
        search.seller_type = new_seller
        search.marketplace = new_platforms[0]

    if keywords_changed:
        # Changed filters change the result set; record it silently again so
        # listings that now match are not reported as new.
        for source in search.sources:
            _restart_baseline(source, now)

    if active is not None and active != search.active:
        search.active = active
        if active:
            for source in search.sources:
                source.next_check_at = now
                source.consecutive_failure_count = 0

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
    now = datetime.now(UTC)
    for source in search.sources:
        source.next_check_at = now
    db_session.commit()
    db_session.refresh(search)
    return search


def search_status(search: MarketplaceSearch) -> SearchStatus:
    sources = list(search.sources)
    failing = [source for source in sources if source.last_status not in {"ok", "pending"}]
    if failing:
        status = failing[0].last_status
        message = "; ".join(
            f"{platform_label(source.marketplace)}: {source.last_error_message or source.last_status}"
            for source in failing
        )
    elif sources and all(source.last_status == "ok" for source in sources):
        status, message = "ok", None
    else:
        status, message = "pending", None
    checked = [source.last_checked_at for source in sources if source.last_checked_at]
    scheduled = [source.next_check_at for source in sources if source.next_check_at]
    totals = [source.last_total_count for source in sources if source.last_total_count is not None]
    return SearchStatus(
        baseline_done=bool(sources) and all(source.baseline_done for source in sources),
        last_checked_at=max(checked, key=_aware) if checked else None,
        next_check_at=min(scheduled, key=_aware) if scheduled else None,
        last_status=status,
        last_error_message=message,
        last_total_count=sum(totals) if totals else None,
    )


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


def cheapest_listing(db_session: Session, search: MarketplaceSearch) -> MarketplaceListing | None:
    """Lowest-priced listing that is still online (listings without a price are skipped)."""
    return db_session.scalar(
        select(MarketplaceListing)
        .where(
            MarketplaceListing.search_id == search.id,
            MarketplaceListing.gone_at.is_(None),
            MarketplaceListing.current_price.is_not(None),
        )
        .order_by(MarketplaceListing.current_price.asc(), MarketplaceListing.id.asc())
        .limit(1)
    )


def is_listing_new(listing: MarketplaceListing, now: datetime | None = None) -> bool:
    return _is_new(listing.from_baseline, listing.first_seen_at, now or datetime.now(UTC))


def get_search_filters(search: MarketplaceSearch) -> SearchFilters | None:
    if not search.filters_json:
        return None
    return SearchFilters.from_dict(json.loads(search.filters_json))


def get_search_description(search: MarketplaceSearch) -> list[str]:
    return list(json.loads(search.description_json or "[]"))


def get_exclude_keywords(search: MarketplaceSearch) -> list[str]:
    return list(json.loads(search.exclude_keywords_json or "[]"))


def get_post_filters(source: MarketplaceSearchSource) -> list[str]:
    return list(json.loads(source.post_filters_json or "[]"))


# --- Worker ------------------------------------------------------------------


def run_due_marketplace_searches(
    db_session: Session,
    settings: Settings,
    *,
    adapters: Adapters | None = None,
    notifier=None,
) -> int:
    now = datetime.now(UTC)
    sources = list(
        db_session.scalars(
            select(MarketplaceSearchSource)
            .join(MarketplaceSearch, MarketplaceSearch.id == MarketplaceSearchSource.search_id)
            .where(
                MarketplaceSearch.active.is_(True),
                or_(
                    MarketplaceSearchSource.next_check_at.is_(None),
                    MarketplaceSearchSource.next_check_at <= now,
                ),
            )
            .order_by(
                MarketplaceSearchSource.next_check_at.asc().nullsfirst(),
                MarketplaceSearchSource.id.asc(),
            )
            .limit(DUE_BATCH_SIZE)
        ).all()
    )
    if not sources:
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
    adapters = adapters if adapters is not None else get_adapters()

    processed = 0
    for source in sources:
        processed += 1
        source_id = source.id
        try:
            adapter = adapters.get(source.marketplace)
            if adapter is None:
                raise MarketplaceError("unsupported", f"Unknown platform {source.marketplace}")
            check_source(
                db_session,
                source,
                settings,
                adapter=adapter,
                notifier=notifier,
                alerts_enabled=alerts_enabled,
            )
            db_session.commit()
        except Exception as exc:  # pragma: no cover - safety net
            db_session.rollback()
            metrics.inc("marketplace.search_unhandled_error")
            logger.exception(
                "marketplace_search.unhandled_error source_id=%s reason=%s",
                source_id,
                exc,
            )
            failed = db_session.get(MarketplaceSearchSource, source_id)
            if failed is not None:
                kind = exc.kind if isinstance(exc, MarketplaceError) else "error"
                _record_failure(failed, kind, str(exc), datetime.now(UTC), settings)
                db_session.commit()
    return processed


def check_source(
    db_session: Session,
    source: MarketplaceSearchSource,
    settings: Settings,
    *,
    adapter: PlatformAdapter,
    notifier,
    alerts_enabled: bool,
) -> None:
    search = source.search
    now = datetime.now(UTC)
    source.last_checked_at = now
    source.check_count += 1

    try:
        page = adapter.search(json.loads(source.query_json))
    except MarketplaceError as exc:
        _record_failure(source, exc.kind, str(exc), now, settings)
        return

    baseline = not source.baseline_done
    previous_full_coverage = source.last_complete
    watermark = source.id_watermark
    keywords = get_exclude_keywords(search)
    filters = get_search_filters(search)
    post_filters = get_post_filters(source) if filters is not None else []

    page_ids = {listing.item_id for listing in page.listings}
    matching: list[Listing] = []
    unknown_by_id: dict[str, list[str]] = {}
    for listing in page.listings:
        if _is_excluded(listing, keywords):
            continue
        if post_filters:
            matches, unknown = check_listing(filters, listing, post_filters)
            if not matches:
                continue
            unknown_by_id[listing.item_id] = unknown
        matching.append(listing)
    known = {
        row.item_id: row
        for row in db_session.scalars(
            select(MarketplaceListing).where(
                MarketplaceListing.search_id == search.id,
                MarketplaceListing.item_id.in_([listing.item_id for listing in matching]),
            )
        ).all()
    }

    policy = search.unknown_policy
    elsewhere: set[str] = set()
    intents: list[_AlertIntent] = []
    for listing in matching:
        unknown = unknown_by_id.get(listing.item_id, [])
        row = known.get(listing.item_id)
        if row is not None and row.marketplace != source.marketplace:
            # Shown on several platforms under one id (e.g. a Marktplaats ad also
            # on 2dehands): recorded once, by the platform that found it first.
            elsewhere.add(listing.item_id)
            continue
        if unknown and policy == "exclude":
            if row is not None:
                _delete_listing_rows(db_session, [row])
            continue
        if unknown and policy == "quiet":
            if row is None:
                _create_listing_row(db_session, search, listing, now, baseline, unknown)
            else:
                _update_listing_row(row, listing, now, unknown)
            continue
        if row is None:
            row = _create_listing_row(db_session, search, listing, now, baseline, unknown)
            if baseline:
                continue
            if not _counts_as_new(listing, watermark, previous_full_coverage):
                logger.info(
                    "marketplace_search.older_listing search_id=%s item_id=%s",
                    search.id,
                    listing.item_id,
                )
            elif _within_ceiling(search, listing.price):
                intents.append(
                    _AlertIntent(
                        kind="new_listing", row=row, listing=listing, unknown_filters=unknown
                    )
                )
            continue

        old_price = row.current_price
        _update_listing_row(row, listing, now, unknown)
        if (
            listing.price is not None
            and old_price is not None
            and listing.price < old_price
            and _within_ceiling(search, listing.price)
        ):
            intents.append(
                _AlertIntent(
                    kind="price_drop",
                    row=row,
                    listing=listing,
                    old_price=old_price,
                    unknown_filters=unknown,
                )
            )

    archive = settings.marketplace_archive_enabled and source.marketplace in ARCHIVE_MARKETPLACES
    if policy == "exclude":
        matching = [listing for listing in matching if not unknown_by_id.get(listing.item_id)]
    matching = [listing for listing in matching if listing.item_id not in elsewhere]
    if archive:
        observe_listings(db_session, search, matching, now)

    if page.complete:
        # The page holds the complete result set, so anything missing is gone.
        missing: list[str] = []
        for row in db_session.scalars(
            select(MarketplaceListing).where(
                MarketplaceListing.search_id == search.id,
                MarketplaceListing.marketplace == source.marketplace,
                MarketplaceListing.gone_at.is_(None),
            )
        ).all():
            if row.item_id not in page_ids:
                row.gone_at = now
                missing.append(row.item_id)
        if archive:
            mark_listings_missing(db_session, source.marketplace, missing, now)

    ids = [value for listing in page.listings if (value := listing.numeric_id) is not None]
    if ids:
        source.id_watermark = max([*ids, watermark or 0])
    source.baseline_done = True
    source.last_total_count = page.total_count
    source.last_fetched_count = len(page.listings)
    source.last_complete = page.complete
    source.last_status = "ok"
    source.last_error_message = None
    source.consecutive_failure_count = 0
    jitter = max(0, settings.marketplace_check_jitter_seconds)
    source.next_check_at = now + timedelta(
        seconds=max(60, settings.marketplace_check_interval_seconds)
        + random.randint(-jitter, jitter)
    )
    db_session.flush()

    metrics.inc("marketplace.search_checked")
    logger.info(
        "marketplace_search.ok search_id=%s platform=%s baseline=%s total=%s fetched=%s "
        "matching=%s alerts=%s",
        search.id,
        source.marketplace,
        baseline,
        page.total_count,
        len(page.listings),
        len(matching),
        len(intents),
    )

    if intents and alerts_enabled:
        _dispatch_alerts(db_session, search, intents, notifier, now)


def _ordered(adapters: Adapters) -> list[tuple[str, PlatformAdapter]]:
    order = list(PLATFORM_LABELS)
    return sorted(
        adapters.items(),
        key=lambda item: order.index(item[0]) if item[0] in order else len(order),
    )


def _merge(merged: dict[str, MergedOption], label: str, platform: str) -> None:
    option = merged.setdefault(normalize_label(label), MergedOption(label=label))
    if platform not in option.platforms:
        option.platforms.append(platform)


def _validate_platforms(adapters: Adapters, platforms: list[str]) -> list[str]:
    result: list[str] = []
    for key in platforms:
        if key not in adapters:
            raise ValueError(f"Unknown platform: {key}")
        if key not in result:
            result.append(key)
    if not result:
        raise ValueError("Choose at least one platform")
    order = [key for key, _ in _ordered(adapters)]
    return sorted(result, key=order.index)


def _validate_unknown_policy(policy: str) -> None:
    if policy not in UNKNOWN_POLICIES:
        raise ValueError(f"Unknown policy for missing values: {policy}")


def _validate_seller_type(seller_type: str | None) -> None:
    if seller_type not in SELLER_TYPES:
        raise ValueError(f"Unknown seller type: {seller_type}")


def _build_queries(
    adapters: Adapters, filters: SearchFilters, platforms: list[str], seller_type: str
) -> dict[str, PlatformQuery]:
    return {key: adapters[key].build_query(filters, seller_type) for key in platforms}


def _new_source(key: str, built: PlatformQuery, now: datetime) -> MarketplaceSearchSource:
    return MarketplaceSearchSource(
        marketplace=key,
        query_json=json.dumps(built.query),
        post_filters_json=json.dumps(built.post_filters),
        baseline_done=False,
        last_complete=False,
        last_status="pending",
        consecutive_failure_count=0,
        check_count=0,
        next_check_at=now,
    )


def _sync_sources(
    db_session: Session,
    search: MarketplaceSearch,
    queries: dict[str, PlatformQuery],
    now: datetime,
) -> None:
    """Add, update and remove sources; only changed queries start a new baseline."""
    existing = {source.marketplace: source for source in search.sources}
    successors = {old: new for new, old in SHARED_LISTING_IDS.items() if new in queries}
    for key, source in existing.items():
        if key not in queries:
            search.sources.remove(source)
            if key in successors:
                # Same listings under the same ids: keep them and their history.
                _move_platform_listings(db_session, search, key, successors[key])
            else:
                _delete_platform_listings(db_session, search, key)
    for key, built in queries.items():
        source = existing.get(key)
        if source is None:
            search.sources.append(_new_source(key, built, now))
            continue
        if _canonical(json.loads(source.query_json)) == _canonical(built.query) and sorted(
            get_post_filters(source)
        ) == sorted(built.post_filters):
            continue
        source.query_json = json.dumps(built.query)
        source.post_filters_json = json.dumps(built.post_filters)
        _restart_baseline(source, now)


def _restart_baseline(source: MarketplaceSearchSource, now: datetime) -> None:
    source.baseline_done = False
    source.last_complete = False
    source.next_check_at = now


def _delete_platform_listings(db_session: Session, search: MarketplaceSearch, key: str) -> None:
    _delete_listing_rows(
        db_session,
        db_session.scalars(
            select(MarketplaceListing).where(
                MarketplaceListing.search_id == search.id, MarketplaceListing.marketplace == key
            )
        ).all(),
    )


def _delete_listing_rows(db_session: Session, rows: list[MarketplaceListing]) -> None:
    ids = [row.id for row in rows]
    if ids:
        db_session.execute(
            delete(MarketplaceAlertEvent).where(MarketplaceAlertEvent.listing_id.in_(ids))
        )
    for row in rows:
        db_session.delete(row)


def _move_platform_listings(
    db_session: Session, search: MarketplaceSearch, old: str, new: str
) -> None:
    for row in db_session.scalars(
        select(MarketplaceListing).where(
            MarketplaceListing.search_id == search.id, MarketplaceListing.marketplace == old
        )
    ).all():
        row.marketplace = new


def _canonical(value: Any) -> Any:
    """Order-insensitive form of a query, to tell real changes from reordering."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return sorted((_canonical(item) for item in value), key=lambda item: json.dumps(item))
    return value


def _counts_as_new(
    listing: Listing, watermark: int | None, previous_full_coverage: bool
) -> bool:
    if previous_full_coverage or watermark is None:
        return True
    numeric_id = listing.numeric_id
    return numeric_id is not None and numeric_id > watermark


def _within_ceiling(search: MarketplaceSearch, price: Decimal | None) -> bool:
    ceiling = search.alert_max_price
    return ceiling is not None and price is not None and price <= ceiling


def _validate_ceiling(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value <= 0:
        raise ValueError("The price ceiling must be positive")
    return value.quantize(Decimal("0.01"))


def _is_excluded(listing: Listing, keywords: list[str]) -> bool:
    if not keywords:
        return False
    haystack = f"{listing.title}\n{listing.description}".lower()
    return any(keyword in haystack for keyword in keywords)


def _is_new(from_baseline: bool, first_seen_at: datetime, now: datetime) -> bool:
    if from_baseline:
        return False
    return now - _aware(first_seen_at) <= NEW_LISTING_WINDOW


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _create_listing_row(
    db_session: Session,
    search: MarketplaceSearch,
    listing: Listing,
    now: datetime,
    baseline: bool,
    unknown_filters: list[str],
) -> MarketplaceListing:
    row = MarketplaceListing(
        search_id=search.id,
        marketplace=listing.marketplace,
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
        unverified_filters_json=json.dumps(unknown_filters),
        from_baseline=baseline,
        first_seen_at=now,
        last_seen_at=now,
    )
    if listing.price is not None:
        row.prices.append(MarketplaceListingPrice(price=listing.price, observed_at=now))
    db_session.add(row)
    return row


def _update_listing_row(
    row: MarketplaceListing, listing: Listing, now: datetime, unknown_filters: list[str]
) -> None:
    row.title = listing.title[:512]
    row.url = listing.url
    row.image_url = listing.image_url or row.image_url
    row.price_type = listing.price_type
    row.city = listing.city
    row.distance_meters = listing.distance_meters
    row.attributes_json = json.dumps(listing.attributes, ensure_ascii=False)
    row.unverified_filters_json = json.dumps(unknown_filters)
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
    source: MarketplaceSearchSource,
    kind: str,
    message: str,
    now: datetime,
    settings: Settings,
) -> None:
    source.consecutive_failure_count += 1
    backoff = max(1, settings.retry_interval_seconds) * (
        max(1, settings.retry_backoff_multiplier)
        ** max(source.consecutive_failure_count - 1, 0)
    )
    backoff = min(backoff, max(1, settings.retry_max_interval_seconds))
    source.last_status = kind
    source.last_error_message = message[:512]
    source.next_check_at = now + timedelta(seconds=backoff)
    metrics.inc(f"marketplace.search_failed.{kind}")
    logger.warning(
        "marketplace_search.failed search_id=%s platform=%s kind=%s failures=%s reason=%s",
        source.search_id,
        source.marketplace,
        kind,
        source.consecutive_failure_count,
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

    show_platform = len(search.sources) > 1
    for intent in pending[:MAX_ALERTS_PER_CHECK]:
        message = format_listing_message(
            search,
            intent.kind,
            intent.listing,
            intent.old_price,
            show_platform=show_platform,
            unknown_filters=intent.unknown_filters,
        )
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
        # Guard against floods (e.g. after a platform change); the listings
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
    *,
    show_platform: bool = False,
    unknown_filters: list[str] | None = None,
) -> NotificationMessage:
    suffix = f" ({platform_label(listing.marketplace)})" if show_platform else ""
    if kind == "price_drop" and old_price is not None and listing.price is not None:
        title = f"📉 Prijsdaling — {search.name}{suffix}"
        price_line = (
            f"💶 {format_euro(old_price)} → {format_euro(listing.price)}"
            f" (−{format_euro(old_price - listing.price)})"
        )
    else:
        title = f"🆕 Nieuwe advertentie — {search.name}{suffix}"
        price_line = f"💶 {_format_listing_price(listing)}"

    lines = [listing.title, price_line]
    details = _car_details(listing.attributes)
    if details:
        lines.append(f"🚗 {details}")
    place = _place_line(listing, search)
    if place:
        lines.append(f"📍 {place}")
    if unknown_filters:
        labels = ", ".join(FILTER_LABELS[key].lower() for key in unknown_filters)
        lines.append(f"❔ Niet vermeld: {labels}")
    lines.append(listing.url)
    return NotificationMessage(
        title=title, body="\n".join(lines), photo_url=listing.image_url
    )


def _flag(country: str | None) -> str:
    """Regional-indicator flag emoji for a two-letter country code."""
    if not country or len(country) != 2 or not country.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in country.upper())


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
        flag = _flag(listing.attributes.get("country"))
        parts.append(f"{flag} {listing.city}" if flag else listing.city)
    if listing.distance_meters is not None:
        home = home_location()
        suffix = f" van {home.name}" if home is not None else ""
        parts.append(f"{round(listing.distance_meters / 1000)} km{suffix}")
    seller = _SELLER_LABELS.get(listing.seller_type or _seller_from_filter(search) or "")
    if seller:
        parts.append(seller)
    return " · ".join(parts)
