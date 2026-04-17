from __future__ import annotations

from snipebot.core.config import Settings
from snipebot.notifications.base import Notifier
from snipebot.notifications.noop import NoopNotifier
from snipebot.notifications.telegram import TelegramNotifier


def build_notifier(
    settings: Settings,
    *,
    notifications_enabled: bool | None = None,
    telegram_enabled: bool | None = None,
    telegram_bot_token: str | None = None,
    telegram_chat_id: str | None = None,
) -> Notifier:
    notifications_enabled_value = (
        settings.notifications_enabled
        if notifications_enabled is None
        else notifications_enabled
    )
    telegram_enabled_value = (
        settings.telegram_enabled if telegram_enabled is None else telegram_enabled
    )
    telegram_bot_token_value = (
        settings.telegram_bot_token
        if telegram_bot_token is None
        else telegram_bot_token
    )
    telegram_chat_id_value = (
        settings.telegram_chat_id if telegram_chat_id is None else telegram_chat_id
    )

    if not notifications_enabled_value:
        return NoopNotifier()

    if (
        telegram_enabled_value
        and telegram_bot_token_value.strip()
        and telegram_chat_id_value.strip()
    ):
        return TelegramNotifier(
            bot_token=telegram_bot_token_value.strip(),
            chat_id=telegram_chat_id_value.strip(),
        )

    return NoopNotifier()
