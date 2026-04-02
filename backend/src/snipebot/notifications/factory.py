from __future__ import annotations

from snipebot.core.config import Settings
from snipebot.notifications.base import Notifier
from snipebot.notifications.noop import NoopNotifier
from snipebot.notifications.telegram import TelegramNotifier


def build_notifier(settings: Settings) -> Notifier:
    if not settings.notifications_enabled:
        return NoopNotifier()

    if (
        settings.telegram_enabled
        and settings.telegram_bot_token.strip()
        and settings.telegram_chat_id.strip()
    ):
        return TelegramNotifier(
            bot_token=settings.telegram_bot_token.strip(),
            chat_id=settings.telegram_chat_id.strip(),
        )

    return NoopNotifier()
