from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import detect_site_key
from snipebot.persistence.models import PriceCheck, WatchItem

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
