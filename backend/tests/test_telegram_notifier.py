from io import BytesIO
from urllib.parse import parse_qs
from urllib.error import HTTPError

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


def test_telegram_notifier_http_error_returns_telegram_description(monkeypatch) -> None:
    def _fake_urlopen(request, timeout: int):
        raise HTTPError(
            url=request.full_url,
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=BytesIO(b'{"ok":false,"description":"bot was blocked by the user"}'),
        )

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)
    notifier = TelegramNotifier(bot_token="token", chat_id="chat")

    result = notifier.send(NotificationMessage(title="A", body="B"))

    assert result.ok is False
    assert result.error == "bot was blocked by the user"


def test_telegram_notifier_sends_photo_with_caption(monkeypatch) -> None:
    captured = []

    def _fake_urlopen(request, timeout: int):
        captured.append((request.full_url, parse_qs(request.data.decode("utf-8"))))
        return _FakeResponse('{"ok":true,"result":{"message_id":8}}')

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)
    notifier = TelegramNotifier(bot_token="abc123", chat_id="chat-42")

    result = notifier.send(
        NotificationMessage(title="🆕 New", body="Golf", photo_url="https://img.test/1.jpg")
    )

    assert result.ok is True
    assert result.provider_message_id == "8"
    assert captured == [
        (
            "https://api.telegram.org/botabc123/sendPhoto",
            {
                "chat_id": ["chat-42"],
                "photo": ["https://img.test/1.jpg"],
                "caption": ["🆕 New\nGolf"],
            },
        )
    ]


def test_telegram_notifier_falls_back_to_text_when_photo_fails(monkeypatch) -> None:
    urls = []

    def _fake_urlopen(request, timeout: int):
        urls.append(request.full_url)
        if request.full_url.endswith("/sendPhoto"):
            return _FakeResponse('{"ok":false,"description":"wrong file identifier"}')
        return _FakeResponse('{"ok":true,"result":{"message_id":9}}')

    monkeypatch.setattr("snipebot.notifications.telegram.urlopen", _fake_urlopen)
    notifier = TelegramNotifier(bot_token="t", chat_id="c")

    result = notifier.send(
        NotificationMessage(title="A", body="B", photo_url="https://img.test/broken.jpg")
    )

    assert result.ok is True
    assert result.provider_message_id == "9"
    assert [url.rsplit("/", 1)[1] for url in urls] == ["sendPhoto", "sendMessage"]
