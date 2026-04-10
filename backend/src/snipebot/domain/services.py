from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import detect_site_key
from snipebot.persistence.models import (
    AlertEvent,
    PriceCheck,
    WatchItem,
    WatchItemTag,
)

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "ref",
    "ref_src",
    "source",
}


def _normalize_tag_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Tag name cannot be empty")
    if len(cleaned) > 64:
        raise ValueError("Tag name cannot exceed 64 characters")
    return cleaned


def _normalize_tag_list(values: list[str] | None) -> list[str]:
    if not values:
        return []

    dedup: dict[str, str] = {}
    for value in values:
        normalized = _normalize_tag_name(value)
        key = normalized.lower()
        dedup[key] = normalized
    return sorted(dedup.values(), key=lambda tag: tag.lower())


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
        existing.dead_lettered_at = None
        existing.dead_letter_reason = None
        existing.consecutive_failure_count = 0
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
    tag: str | None = None,
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

    cleaned_tag = tag.strip() if tag else ""
    if cleaned_tag:
        statement = statement.where(
            WatchItem.tags.any(func.lower(WatchItemTag.name) == cleaned_tag.lower())
        )

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
    elif sort == "label_asc":
        statement = statement.order_by(
            func.lower(func.coalesce(WatchItem.custom_label, "")).asc(),
            WatchItem.id.asc(),
        )
    elif sort == "label_desc":
        statement = statement.order_by(
            func.lower(func.coalesce(WatchItem.custom_label, "")).desc(),
            WatchItem.id.desc(),
        )
    elif sort == "site_asc":
        statement = statement.order_by(
            func.lower(WatchItem.site_key).asc(),
            WatchItem.id.asc(),
        )
    elif sort == "site_desc":
        statement = statement.order_by(
            func.lower(WatchItem.site_key).desc(),
            WatchItem.id.desc(),
        )
    elif sort == "target_asc":
        statement = statement.order_by(
            func.coalesce(WatchItem.target_price, 99999999).asc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    elif sort == "target_desc":
        statement = statement.order_by(
            func.coalesce(WatchItem.target_price, -1).desc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    elif sort == "current_asc":
        statement = statement.order_by(
            func.coalesce(WatchItem.current_price, 99999999).asc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    elif sort == "current_desc":
        statement = statement.order_by(
            func.coalesce(WatchItem.current_price, -1).desc(),
            WatchItem.updated_at.desc(),
            WatchItem.id.desc(),
        )
    elif sort == "status_asc":
        statement = statement.order_by(
            func.lower(func.coalesce(WatchItem.last_status, "")).asc(),
            WatchItem.id.asc(),
        )
    elif sort == "status_desc":
        statement = statement.order_by(
            func.lower(func.coalesce(WatchItem.last_status, "")).desc(),
            WatchItem.id.desc(),
        )
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


def list_watch_tags(db_session: Session, *, owner_id: str) -> list[WatchItemTag]:
    statement = (
        select(WatchItemTag)
        .where(WatchItemTag.owner_id == owner_id)
        .order_by(func.lower(WatchItemTag.name).asc(), WatchItemTag.id.asc())
    )
    return list(db_session.scalars(statement).all())


def get_or_create_watch_tag(
    db_session: Session,
    *,
    owner_id: str,
    name: str,
) -> WatchItemTag:
    normalized = _normalize_tag_name(name)
    existing = db_session.scalar(
        select(WatchItemTag).where(
            WatchItemTag.owner_id == owner_id,
            func.lower(WatchItemTag.name) == normalized.lower(),
        )
    )
    if existing is not None:
        return existing

    tag = WatchItemTag(owner_id=owner_id, name=normalized)
    db_session.add(tag)
    db_session.commit()
    db_session.refresh(tag)
    return tag


def set_watch_item_tags(
    db_session: Session,
    *,
    owner_id: str,
    item_id: int,
    tag_names: list[str],
) -> WatchItem | None:
    item = get_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        return None

    normalized_tags = _normalize_tag_list(tag_names)
    if not normalized_tags:
        item.tags = []
        db_session.commit()
        db_session.refresh(item)
        return item

    statement = select(WatchItemTag).where(
        WatchItemTag.owner_id == owner_id,
        func.lower(WatchItemTag.name).in_([entry.lower() for entry in normalized_tags]),
    )
    existing_tags = list(db_session.scalars(statement).all())
    by_lower = {tag.name.lower(): tag for tag in existing_tags}

    for candidate in normalized_tags:
        if candidate.lower() in by_lower:
            continue
        created = WatchItemTag(owner_id=owner_id, name=candidate)
        db_session.add(created)
        db_session.flush()
        by_lower[candidate.lower()] = created

    item.tags = [by_lower[entry.lower()] for entry in normalized_tags]
    db_session.commit()
    db_session.refresh(item)
    return item


def export_watch_items_rows(
    db_session: Session,
    *,
    owner_id: str,
    active: bool | None = None,
    site_key: str | None = None,
    has_target: bool | None = None,
    query: str | None = None,
    sort: str = "updated_desc",
    include_archived: bool = False,
    archived_only: bool = False,
    tag: str | None = None,
) -> list[dict[str, object]]:
    items, _, _, _ = list_watch_items_paginated(
        db_session,
        owner_id=owner_id,
        active=active,
        site_key=site_key,
        has_target=has_target,
        query=query,
        sort=sort,
        limit=1000,
        offset=0,
        include_archived=include_archived,
        archived_only=archived_only,
        tag=tag,
    )

    rows: list[dict[str, object]] = []
    for item in items:
        rows.append(
            {
                "id": item.id,
                "url": item.url,
                "custom_label": item.custom_label,
                "target_price": float(item.target_price)
                if item.target_price is not None
                else None,
                "site_key": item.site_key,
                "active": item.active,
                "archived_at": item.archived_at.isoformat()
                if item.archived_at
                else None,
                "tags": [
                    tag.name
                    for tag in sorted(item.tags, key=lambda entry: entry.name.lower())
                ],
            }
        )
    return rows


def import_watch_items_rows(
    db_session: Session,
    *,
    owner_id: str,
    rows: list[dict[str, object]],
    dry_run: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    row_results: list[dict[str, object]] = []
    created = 0
    updated = 0
    errored = 0

    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("Each row must be an object")

            url = str(row.get("url", "")).strip()
            if not url:
                raise ValueError("url is required")

            custom_label_raw = row.get("custom_label")
            custom_label = (
                str(custom_label_raw).strip()
                if custom_label_raw not in {None, ""}
                else None
            )

            target_raw = row.get("target_price")
            target_price: Decimal | None = None
            if target_raw not in {None, ""}:
                target_price = Decimal(str(target_raw))
                if target_price <= 0:
                    raise ValueError("target_price must be positive")

            notes_raw = row.get("notes")
            notes = str(notes_raw).strip() if notes_raw not in {None, ""} else None

            tags_raw = row.get("tags")
            if tags_raw is None:
                tag_names: list[str] = []
            elif isinstance(tags_raw, list):
                tag_names = [str(entry) for entry in tags_raw]
            elif isinstance(tags_raw, str):
                tag_names = [
                    entry.strip() for entry in tags_raw.split(",") if entry.strip()
                ]
            else:
                raise ValueError("tags must be a list or comma-separated string")

            normalized_url = normalize_product_url(url)
            existing = db_session.scalar(
                select(WatchItem).where(
                    WatchItem.owner_id == owner_id,
                    WatchItem.normalized_url == normalized_url,
                )
            )
            operation = "updated" if existing is not None else "created"

            row_results.append(
                {
                    "row": index,
                    "status": operation,
                    "url": url,
                    "normalized_url": normalized_url,
                }
            )

            if operation == "created":
                created += 1
            else:
                updated += 1

            if dry_run:
                continue

            item, _ = upsert_watch_item(
                db_session,
                owner_id=owner_id,
                url=url,
                custom_label=custom_label,
                target_price=target_price,
            )
            if notes is not None:
                update_watch_item(
                    db_session,
                    owner_id=owner_id,
                    item_id=item.id,
                    notes=notes,
                    set_notes=True,
                )
            set_watch_item_tags(
                db_session,
                owner_id=owner_id,
                item_id=item.id,
                tag_names=tag_names,
            )
        except Exception as exc:
            errored += 1
            row_results.append(
                {
                    "row": index,
                    "status": "error",
                    "error": str(exc),
                }
            )

    summary = {
        "created": created,
        "updated": updated,
        "error": errored,
    }
    return row_results, summary


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
    item.dead_lettered_at = None
    item.dead_letter_reason = None
    item.consecutive_failure_count = 0
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


def get_watchlist_health_summary(
    db_session: Session,
    *,
    owner_id: str,
    stale_after_seconds: int,
) -> dict[str, int]:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=max(60, stale_after_seconds))

    base = select(WatchItem).where(WatchItem.owner_id == owner_id)
    total = db_session.scalar(select(func.count()).select_from(base.subquery())) or 0
    active = (
        db_session.scalar(
            select(func.count()).select_from(
                base.where(WatchItem.active.is_(True)).subquery()
            )
        )
        or 0
    )
    archived = (
        db_session.scalar(
            select(func.count()).select_from(
                base.where(WatchItem.archived_at.is_not(None)).subquery()
            )
        )
        or 0
    )
    stale = (
        db_session.scalar(
            select(func.count()).select_from(
                base.where(
                    WatchItem.active.is_(True),
                    WatchItem.last_checked_at.is_not(None),
                    WatchItem.last_checked_at < stale_before,
                ).subquery()
            )
        )
        or 0
    )
    error = (
        db_session.scalar(
            select(func.count()).select_from(
                base.where(
                    WatchItem.last_status.notin_(["ok", "pending"]),
                    WatchItem.last_checked_at.is_not(None),
                ).subquery()
            )
        )
        or 0
    )
    dead_lettered = (
        db_session.scalar(
            select(func.count()).select_from(
                base.where(WatchItem.dead_lettered_at.is_not(None)).subquery()
            )
        )
        or 0
    )

    return {
        "total": int(total),
        "active": int(active),
        "archived": int(archived),
        "stale": int(stale),
        "error": int(error),
        "dead_lettered": int(dead_lettered),
    }
