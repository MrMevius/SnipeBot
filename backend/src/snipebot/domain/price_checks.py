from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import get_adapter
from snipebot.core.config import Settings
from snipebot.domain.alerts import AlertContext, decide_alerts, format_alert_message
from snipebot.notifications.factory import build_notifier
from snipebot.persistence.models import AlertEvent, PriceCheck, WatchItem

logger = logging.getLogger(__name__)


def run_due_price_checks(db_session: Session, settings: Settings) -> int:
    items = _get_due_items(db_session, settings.worker_batch_size)
    processed = 0
    notifier = build_notifier(settings)

    for item in items:
        processed += 1
        try:
            _run_check_for_item(db_session, item, settings, notifier=notifier)
            db_session.commit()
        except Exception as exc:  # pragma: no cover - safety net
            db_session.rollback()
            logger.exception(
                "price_check.unhandled_error watch_item_id=%s site_key=%s reason=%s",
                item.id,
                item.site_key,
                exc,
            )

    return processed


def _get_due_items(db_session: Session, limit: int) -> list[WatchItem]:
    now = datetime.now(UTC)
    statement = (
        select(WatchItem)
        .where(
            WatchItem.active.is_(True),
            or_(WatchItem.next_check_at.is_(None), WatchItem.next_check_at <= now),
        )
        .order_by(WatchItem.next_check_at.asc().nullsfirst(), WatchItem.id.asc())
        .limit(limit)
    )
    return list(db_session.scalars(statement).all())


def _run_check_for_item(
    db_session: Session,
    item: WatchItem,
    settings: Settings,
    *,
    notifier,
) -> None:
    checked_at = datetime.now(UTC)
    item.last_checked_at = checked_at
    item.check_count += 1
    previous_successful_price = item.current_price

    adapter = get_adapter(item.site_key)
    if adapter is None:
        _record_failure(
            db_session,
            item,
            checked_at=checked_at,
            status="unsupported",
            error_kind="unsupported_adapter",
            error_message=f"No adapter for site_key={item.site_key}",
            retry_seconds=settings.retry_interval_seconds,
            adapter_key=item.site_key,
            used_fallback=False,
        )
        return

    fallback_allowed = settings.playwright_fallback_enabled and adapter.site_key in {
        key.strip()
        for key in settings.playwright_fallback_adapters.split(",")
        if key.strip()
    }

    result = adapter.check(
        item.normalized_url, allow_playwright_fallback=fallback_allowed
    )
    if result.ok and result.data is not None:
        item.current_price = result.data.current_price
        item.last_status = "ok"
        item.last_error_kind = None
        item.last_error_message = None
        item.successful_check_count += 1
        item.next_check_at = checked_at + timedelta(
            seconds=settings.check_interval_seconds
        )

        check = PriceCheck(
            watch_item_id=item.id,
            checked_at=checked_at,
            adapter_key=adapter.site_key,
            status="ok",
            title=result.data.title,
            current_price=result.data.current_price,
            currency=result.data.currency,
            availability=result.data.availability,
            parser_metadata=result.data.parser_metadata,
            used_fallback=result.used_fallback,
        )
        db_session.add(check)
        db_session.flush()

        _dispatch_alerts_for_success(
            db_session,
            item=item,
            check=check,
            checked_at=checked_at,
            previous_successful_price=previous_successful_price,
            settings=settings,
            notifier=notifier,
        )
        logger.info(
            "price_check.ok watch_item_id=%s adapter=%s price=%s currency=%s used_fallback=%s",
            item.id,
            adapter.site_key,
            result.data.current_price,
            result.data.currency,
            result.used_fallback,
        )
        return

    _record_failure(
        db_session,
        item,
        checked_at=checked_at,
        status=result.status,
        error_kind=result.error_kind or "unknown",
        error_message=result.error_message,
        retry_seconds=settings.retry_interval_seconds,
        adapter_key=adapter.site_key,
        used_fallback=result.used_fallback,
    )


def _record_failure(
    db_session: Session,
    item: WatchItem,
    *,
    checked_at: datetime,
    status: str,
    error_kind: str,
    error_message: str | None,
    retry_seconds: int,
    adapter_key: str,
    used_fallback: bool,
) -> None:
    item.last_status = status
    item.last_error_kind = error_kind
    item.last_error_message = error_message
    item.next_check_at = checked_at + timedelta(seconds=retry_seconds)

    db_session.add(
        PriceCheck(
            watch_item_id=item.id,
            checked_at=checked_at,
            adapter_key=adapter_key,
            status=status,
            error_kind=error_kind,
            error_message=error_message,
            used_fallback=used_fallback,
        )
    )

    logger.warning(
        "price_check.failed watch_item_id=%s adapter=%s status=%s error_kind=%s used_fallback=%s",
        item.id,
        adapter_key,
        status,
        error_kind,
        used_fallback,
    )


def _dispatch_alerts_for_success(
    db_session: Session,
    *,
    item: WatchItem,
    check: PriceCheck,
    checked_at: datetime,
    previous_successful_price,
    settings: Settings,
    notifier,
) -> None:
    intents = decide_alerts(
        previous_successful_price=previous_successful_price,
        new_price=check.current_price,
        target_price=item.target_price,
    )
    if not intents:
        return

    if not settings.notifications_enabled:
        return

    context = AlertContext(
        watch_item_id=item.id,
        label_or_title=item.custom_label or check.title or "Product",
        site_key=item.site_key,
        url=item.url,
        checked_at=checked_at,
    )

    for intent in intents:
        existing = db_session.scalar(
            select(AlertEvent.id)
            .where(
                AlertEvent.watch_item_id == item.id,
                AlertEvent.alert_kind == intent.kind,
                AlertEvent.dedup_key == intent.dedup_key,
                AlertEvent.delivery_status == "sent",
            )
            .limit(1)
        )
        if existing is not None:
            logger.info(
                "alert.dedup_suppressed watch_item_id=%s alert_kind=%s dedup_key=%s",
                item.id,
                intent.kind,
                intent.dedup_key,
            )
            continue

        message = format_alert_message(intent, context)

        response = notifier.send(message)
        delivery_status = "sent" if response.ok else "failed"
        provider_message_id = response.provider_message_id
        error_message = None if response.ok else response.error

        db_session.add(
            AlertEvent(
                watch_item_id=item.id,
                price_check_id=check.id,
                alert_kind=intent.kind,
                dedup_key=intent.dedup_key,
                channel="telegram",
                delivery_status=delivery_status,
                sent_at=checked_at,
                provider_message_id=provider_message_id,
                label_or_title=context.label_or_title,
                site_key=context.site_key,
                product_url=context.url,
                old_price=intent.old_price,
                new_price=intent.new_price,
                target_price=intent.target_price,
                message_text=message.text,
                error_message=error_message,
            )
        )

        if delivery_status == "sent":
            logger.info(
                "alert.sent watch_item_id=%s alert_kind=%s channel=telegram",
                item.id,
                intent.kind,
            )
        else:
            logger.warning(
                "alert.failed watch_item_id=%s alert_kind=%s channel=telegram reason=%s",
                item.id,
                intent.kind,
                error_message,
            )
