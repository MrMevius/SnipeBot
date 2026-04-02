from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from snipebot.notifications.models import NotificationMessage


@dataclass(slots=True)
class AlertIntent:
    kind: str
    old_price: Decimal | None
    new_price: Decimal
    target_price: Decimal | None

    @property
    def dedup_key(self) -> str:
        old_part = f"{self.old_price:.2f}" if self.old_price is not None else "none"
        target_part = (
            f"{self.target_price:.2f}" if self.target_price is not None else "none"
        )
        return (
            f"{self.kind}|old={old_part}|new={self.new_price:.2f}|target={target_part}"
        )


@dataclass(slots=True)
class AlertContext:
    watch_item_id: int
    label_or_title: str
    site_key: str
    url: str
    checked_at: datetime


def decide_alerts(
    *,
    previous_successful_price: Decimal | None,
    new_price: Decimal,
    target_price: Decimal | None,
) -> list[AlertIntent]:
    intents: list[AlertIntent] = []

    if previous_successful_price is not None and new_price < previous_successful_price:
        intents.append(
            AlertIntent(
                kind="price_drop",
                old_price=previous_successful_price,
                new_price=new_price,
                target_price=target_price,
            )
        )

    if target_price is not None and new_price <= target_price:
        was_above_target = (
            previous_successful_price is None
            or previous_successful_price > target_price
        )
        if was_above_target:
            intents.append(
                AlertIntent(
                    kind="target_reached",
                    old_price=previous_successful_price,
                    new_price=new_price,
                    target_price=target_price,
                )
            )

    return intents


def format_alert_message(
    intent: AlertIntent, context: AlertContext
) -> NotificationMessage:
    old_price = (
        f"€{intent.old_price:.2f}" if intent.old_price is not None else "unknown"
    )
    new_price = f"€{intent.new_price:.2f}"

    if intent.kind == "target_reached":
        target = (
            f"€{intent.target_price:.2f}" if intent.target_price is not None else "n/a"
        )
        title = "🎯 Target reached"
        body = (
            f"{context.label_or_title} [{context.site_key}]\n"
            f"Old: {old_price} → New: {new_price}\n"
            f"Target: {target}\n"
            f"{context.url}"
        )
        return NotificationMessage(title=title, body=body)

    title = "📉 Price drop"
    body = (
        f"{context.label_or_title} [{context.site_key}]\n"
        f"Old: {old_price} → New: {new_price}\n"
        f"{context.url}"
    )
    return NotificationMessage(title=title, body=body)


def utcnow() -> datetime:
    return datetime.now(UTC)
