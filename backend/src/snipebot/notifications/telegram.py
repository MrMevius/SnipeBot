from __future__ import annotations

import json
import logging
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from snipebot.notifications.base import Notifier
from snipebot.notifications.models import NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)

# Telegram limits photo captions to 1024 characters.
CAPTION_LIMIT = 1024


class TelegramNotifier(Notifier):
    def __init__(self, *, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, message: NotificationMessage) -> NotificationResult:
        if message.photo_url and len(message.text) <= CAPTION_LIMIT:
            result = self._call(
                "sendPhoto",
                {
                    "chat_id": self._chat_id,
                    "photo": message.photo_url,
                    "caption": message.text,
                },
            )
            if result.ok:
                return result
            logger.warning(
                "telegram.photo_failed falling back to text reason=%s", result.error
            )

        return self._call(
            "sendMessage",
            {
                "chat_id": self._chat_id,
                "text": message.text,
                "disable_web_page_preview": "true",
            },
        )

    def _call(self, method: str, fields: dict[str, str]) -> NotificationResult:
        endpoint = f"https://api.telegram.org/bot{self._bot_token}/{method}"
        payload = urlencode(fields).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=15) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:  # pragma: no cover - network safety
            response_body = ""
            try:
                response_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                response_body = ""

            if response_body:
                try:
                    decoded = json.loads(response_body)
                    description = decoded.get("description")
                    if description:
                        return NotificationResult(ok=False, error=str(description))
                except json.JSONDecodeError:
                    pass

            return NotificationResult(ok=False, error=f"telegram_http_error_{exc.code}")
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
