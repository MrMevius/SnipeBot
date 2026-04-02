from urllib.parse import parse_qs

from snipebot.notifications.models import NotificationMessage
from snipebot.notifications.telegram import TelegramNotifier


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_telegram_notifier_success(monkeypatch) -> None:
    def _fake_urlopen(request, timeout: int):
        return _FakeResponse('{"ok":true,"result":{"message_id":42}}')

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)
    notifier = TelegramNotifier(bot_token="token", chat_id="chat")

    result = notifier.send(NotificationMessage(title="A", body="B"))

    assert result.ok is True
    assert result.provider_message_id == "42"


def test_telegram_notifier_failure_response(monkeypatch) -> None:
    def _fake_urlopen(request, timeout: int):
        return _FakeResponse('{"ok":false,"description":"Forbidden"}')

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)
    notifier = TelegramNotifier(bot_token="token", chat_id="chat")

    result = notifier.send(NotificationMessage(title="A", body="B"))

    assert result.ok is False
    assert result.error == "Forbidden"


def test_telegram_notifier_generates_expected_payload(monkeypatch) -> None:
    captured = {}

    def _fake_urlopen(request, timeout: int):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["content_type"] = request.headers.get("Content-type")
        captured["timeout"] = timeout
        return _FakeResponse('{"ok":true,"result":{"message_id":7}}')

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)

    notifier = TelegramNotifier(bot_token="abc123", chat_id="chat-42")
    message = NotificationMessage(title="📉 Price drop", body="Line one\nLine two")
    result = notifier.send(message)

    payload = parse_qs(captured["body"])

    assert result.ok is True
    assert captured["url"] == "https://api.telegram.org/botabc123/sendMessage"
    assert captured["timeout"] == 15
    assert captured["content_type"] == "application/x-www-form-urlencoded"
    assert payload["chat_id"] == ["chat-42"]
    assert payload["text"] == ["📉 Price drop\nLine one\nLine two"]
    assert payload["disable_web_page_preview"] == ["true"]
