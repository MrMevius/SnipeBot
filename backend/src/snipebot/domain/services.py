from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import func, select
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
    statement = (
        select(WatchItem)
        .where(WatchItem.owner_id == owner_id)
        .order_by(WatchItem.updated_at.desc(), WatchItem.id.desc())
    )
    return list(db_session.scalars(statement).all())


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
