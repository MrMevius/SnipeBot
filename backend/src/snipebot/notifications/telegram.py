from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snipebot.notifications.base import Notifier
from snipebot.notifications.models import NotificationMessage, NotificationResult


class TelegramNotifier(Notifier):
    def __init__(self, *, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, message: NotificationMessage) -> NotificationResult:
        endpoint = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = urlencode(
            {
                "chat_id": self._chat_id,
                "text": message.text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - network safety
            return NotificationResult(ok=False, error=str(exc))

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            return NotificationResult(ok=False, error="invalid_telegram_response")

        if decoded.get("ok") is not True:
            return NotificationResult(
                ok=False,
                error=str(decoded.get("description") or "telegram_send_failed"),
            )

        provider_message_id = None
        result = decoded.get("result")
        if isinstance(result, dict):
            message_id = result.get("message_id")
            if message_id is not None:
                provider_message_id = str(message_id)

        return NotificationResult(ok=True, provider_message_id=provider_message_id)
