from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import detect_site_key
from snipebot.persistence.models import AlertEvent, PriceCheck, WatchItem

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "ref",
    "ref_src",
    "source",
}


def normalize_product_url(url: str) -> str:
    candidate = url.strip()
    parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must start with http:// or https://")

    if not parsed.hostname:
        raise ValueError("URL must include a valid hostname")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    port = parsed.port
    is_default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = hostname if port is None or is_default_port else f"{hostname}:{port}"

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))

    query = urlencode(sorted(filtered_query), doseq=True)
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def upsert_watch_item(
    db_session: Session,
    *,
    owner_id: str,
    url: str,
    custom_label: str | None,
    target_price: Decimal | None,
) -> tuple[WatchItem, str]:
    normalized_url = normalize_product_url(url)
    site_key = detect_site_key(normalized_url)

    existing = db_session.scalar(
        select(WatchItem).where(
            WatchItem.owner_id == owner_id,
            WatchItem.normalized_url == normalized_url,
        )
    )

    cleaned_label = custom_label.strip() if custom_label else None

    if existing is not None:
        existing.url = url.strip()
        existing.custom_label = cleaned_label
        existing.target_price = target_price
        existing.site_key = site_key
        existing.active = True
        existing.archived_at = None
        if existing.next_check_at is None:
            existing.next_check_at = datetime.now(UTC)
        db_session.commit()
        db_session.refresh(existing)
        return existing, "updated"

    item = WatchItem(
        owner_id=owner_id,
        url=url.strip(),
        normalized_url=normalized_url,
        custom_label=cleaned_label,
        target_price=target_price,
        site_key=site_key,
        active=True,
        last_status="pending",
        next_check_at=datetime.now(UTC),
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item, "created"


def list_watch_items(db_session: Session, *, owner_id: str) -> list[WatchItem]:
    items, _, _, _ = list_watch_items_paginated(
        db_session,
        owner_id=owner_id,
    )
    return items


def list_watch_items_paginated(
    db_session: Session,
    *,
    owner_id: str,
    active: bool | None = None,
    site_key: str | None = None,
    has_target: bool | None = None,
    query: str | None = None,
    sort: str = "updated_desc",
    limit: int = 50,
    offset: int = 0,
    include_archived: bool = False,
    archived_only: bool = False,
) -> tuple[list[WatchItem], int, int, int]:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    statement = select(WatchItem).where(WatchItem.owner_id == owner_id)

    if archived_only:
        statement = statement.where(WatchItem.archived_at.is_not(None))
    elif not include_archived:
        statement = statement.where(WatchItem.archived_at.is_(None))

    if active is not None:
        statement = statement.where(WatchItem.active == active)
    if site_key:
        statement = statement.where(WatchItem.site_key == site_key.strip())
    if has_target is not None:
        if has_target:
            statement = statement.where(WatchItem.target_price.is_not(None))
        else:
            statement = statement.where(WatchItem.target_price.is_(None))

    cleaned_query = query.strip() if query else ""
    if cleaned_query:
        like = f"%{cleaned_query.lower()}%"
        statement = statement.where(
            or_(
                func.lower(WatchItem.custom_label).like(like),
                func.lower(WatchItem.url).like(like),
            )
        )

    if sort == "updated_asc":
        statement = statement.order_by(WatchItem.updated_at.asc(), WatchItem.id.asc())
    elif sort == "price_asc":
        statement = statement.order_by(
            func.coalesce(WatchItem.current_price, 99999999).asc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    elif sort == "price_desc":
        statement = statement.order_by(
            func.coalesce(WatchItem.current_price, -1).desc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    else:
        statement = statement.order_by(WatchItem.updated_at.desc(), WatchItem.id.desc())

    total = (
        db_session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    items = list(
        db_session.scalars(statement.limit(safe_limit).offset(safe_offset)).all()
    )
    return items, total, safe_limit, safe_offset


def bulk_update_watch_items(
    db_session: Session,
    *,
    owner_id: str,
    item_ids: list[int],
    action: str,
    target_price: Decimal | None = None,
) -> tuple[int, list[tuple[int, str]]]:
    if not item_ids:
        return 0, []

    unique_ids = list(dict.fromkeys(item_ids))
    items = list(
        db_session.scalars(
            select(WatchItem).where(
                WatchItem.owner_id == owner_id,
                WatchItem.id.in_(unique_ids),
            )
        ).all()
    )
    by_id = {item.id: item for item in items}

    updated = 0
    failed: list[tuple[int, str]] = []
    now = datetime.now(UTC)

    for item_id in unique_ids:
        item = by_id.get(item_id)
        if item is None:
            failed.append((item_id, "not_found"))
            continue

        if action == "pause":
            item.active = False
        elif action == "resume":
            item.active = True
            if item.archived_at is not None:
                item.archived_at = None
        elif action == "archive":
            item.archived_at = now
            item.active = False
        elif action == "set_target":
            item.target_price = target_price
        else:
            failed.append((item_id, "unsupported_action"))
            continue

        updated += 1

    db_session.commit()
    return updated, failed


def archive_watch_item(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
) -> WatchItem | None:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None

    item.archived_at = datetime.now(UTC)
    item.active = False
    db_session.commit()
    db_session.refresh(item)
    return item


def restore_watch_item(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
) -> WatchItem | None:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None

    item.archived_at = None
    item.active = True
    db_session.commit()
    db_session.refresh(item)
    return item


def deactivate_watch_item(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
) -> WatchItem | None:
    item = db_session.scalar(
        select(WatchItem).where(WatchItem.owner_id == owner_id, WatchItem.id == item_id)
    )
    if item is None:
        return None

    item.active = False
    db_session.commit()
    db_session.refresh(item)
    return item


def get_watch_item(
    db_session: Session, *, owner_id: str, item_id: int
) -> WatchItem | None:
    return db_session.scalar(
        select(WatchItem).where(WatchItem.owner_id == owner_id, WatchItem.id == item_id)
    )


def update_watch_item(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
    custom_label: str | None = None,
    target_price: Decimal | None = None,
    notes: str | None = None,
    active: bool | None = None,
    set_custom_label: bool = False,
    set_target_price: bool = False,
    set_notes: bool = False,
    set_active: bool = False,
) -> WatchItem | None:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None

    if set_custom_label:
        item.custom_label = custom_label.strip() if custom_label else None
    if set_target_price:
        item.target_price = target_price
    if set_notes:
        item.notes = notes.strip() if notes else None
    if set_active:
        item.active = active if active is not None else item.active

    db_session.commit()
    db_session.refresh(item)
    return item


def trigger_watch_item_check_now(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
) -> WatchItem | None:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None

    item.active = True
    item.next_check_at = datetime.now(UTC)
    db_session.commit()
    db_session.refresh(item)
    return item


def get_watch_item_price_history(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
    days: int = 30,
    max_points: int = 200,
) -> tuple[WatchItem | None, list[PriceCheck]]:
    item = db_session.scalar(
        select(WatchItem).where(WatchItem.owner_id == owner_id, WatchItem.id == item_id)
    )
    if item is None:
        return None, []

    safe_days = max(1, min(days, 365))
    safe_limit = max(1, min(max_points, 1000))
    since = datetime.now(UTC) - timedelta(days=safe_days)

    statement = (
        select(PriceCheck)
        .where(
            PriceCheck.watch_item_id == item.id,
            PriceCheck.status == "ok",
            PriceCheck.current_price.is_not(None),
            PriceCheck.checked_at >= since,
        )
        .order_by(PriceCheck.checked_at.asc())
        .limit(safe_limit)
    )

    checks = list(db_session.scalars(statement).all())
    return item, checks


def list_watch_item_alert_events(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
    limit: int = 25,
) -> tuple[WatchItem | None, list[AlertEvent]]:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None, []

    safe_limit = max(1, min(limit, 200))
    statement = (
        select(AlertEvent)
        .where(AlertEvent.watch_item_id == item.id)
        .order_by(AlertEvent.sent_at.desc(), AlertEvent.id.desc())
        .limit(safe_limit)
    )
    return item, list(db_session.scalars(statement).all())


def get_watch_item_lows(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
) -> tuple[WatchItem | None, float | None, float | None, float | None]:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None, None, None, None

    now = datetime.now(UTC)
    seven_days = now - timedelta(days=7)
    thirty_days = now - timedelta(days=30)

    base_filter = (
        PriceCheck.watch_item_id == item.id,
        PriceCheck.status == "ok",
        PriceCheck.current_price.is_not(None),
    )

    all_time_low = db_session.scalar(
        select(func.min(PriceCheck.current_price)).where(*base_filter)
    )
    low_30d = db_session.scalar(
        select(func.min(PriceCheck.current_price)).where(
            *base_filter,
            PriceCheck.checked_at >= thirty_days,
        )
    )
    low_7d = db_session.scalar(
        select(func.min(PriceCheck.current_price)).where(
            *base_filter,
            PriceCheck.checked_at >= seven_days,
        )
    )

    return (
        item,
        float(low_7d) if low_7d is not None else None,
        float(low_30d) if low_30d is not None else None,
        float(all_time_low) if all_time_low is not None else None,
    )
