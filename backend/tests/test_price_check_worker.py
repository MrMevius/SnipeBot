from datetime import UTC, datetime
from decimal import Decimal

from snipebot.adapters.sites.base import AdapterCheckResult, ParsedProductData
from snipebot.core.config import get_settings
from snipebot.domain.price_checks import run_due_price_checks
from snipebot.persistence.db import get_engine, get_session_factory, init_db
from snipebot.persistence.models import AlertEvent, PriceCheck, WatchItem


class _SuccessAdapter:
    site_key = "hema"

    def check(self, url: str, *, allow_playwright_fallback: bool) -> AdapterCheckResult:
        return AdapterCheckResult(
            ok=True,
            status="ok",
            data=ParsedProductData(
                title="Desk lamp",
                current_price=Decimal("19.99"),
                currency="EUR",
                availability="in_stock",
                parser_metadata="test-success",
            ),
        )


class _CrashAdapter:
    site_key = "amazon_nl"

    def check(self, url: str, *, allow_playwright_fallback: bool) -> AdapterCheckResult:
        raise RuntimeError("adapter exploded")


class _ParseErrorAdapter:
    site_key = "hema"

    def check(self, url: str, *, allow_playwright_fallback: bool) -> AdapterCheckResult:
        return AdapterCheckResult(
            ok=False,
            status="parse_error",
            error_kind="parse_error",
            error_message="price selector missing",
        )


class _CollectingNotifier:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    def send(self, message):
        self.sent_messages.append(message.text)

        class _Result:
            ok = True
            provider_message_id = "123"
            error = None

        return _Result()


def _reset_tables() -> None:
    init_db()
    with get_engine().begin() as connection:
        connection.exec_driver_sql("DELETE FROM alert_events")
        connection.exec_driver_sql("DELETE FROM price_checks")
        connection.exec_driver_sql("DELETE FROM watch_items")


def test_worker_continues_when_one_adapter_fails(monkeypatch) -> None:
    _reset_tables()
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    with session_factory() as session:
        first = WatchItem(
            owner_id="local",
            url="https://www.hema.nl/product/1",
            normalized_url="https://www.hema.nl/product/1",
            site_key="hema",
            active=True,
            last_status="pending",
            next_check_at=now,
        )
        second = WatchItem(
            owner_id="local",
            url="https://www.amazon.nl/dp/abc",
            normalized_url="https://www.amazon.nl/dp/abc",
            site_key="amazon_nl",
            active=True,
            last_status="pending",
            next_check_at=now,
        )
        session.add_all([first, second])
        session.commit()

    def _fake_get_adapter(site_key: str):
        if site_key == "hema":
            return _SuccessAdapter()
        if site_key == "amazon_nl":
            return _CrashAdapter()
        return None

    monkeypatch.setattr("snipebot.domain.price_checks.get_adapter", _fake_get_adapter)
    settings = get_settings()

    with session_factory() as session:
        processed = run_due_price_checks(session, settings)
    assert processed == 2

    with session_factory() as session:
        items = session.query(WatchItem).order_by(WatchItem.id.asc()).all()
        checks = session.query(PriceCheck).all()

    assert items[0].last_status == "ok"
    assert items[0].current_price == Decimal("19.99")
    assert items[1].last_status == "pending"
    assert len(checks) == 1


def test_worker_persists_price_history_and_latest_snapshot(monkeypatch) -> None:
    _reset_tables()
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    with session_factory() as session:
        item = WatchItem(
            owner_id="local",
            url="https://www.hema.nl/product/1",
            normalized_url="https://www.hema.nl/product/1",
            site_key="hema",
            active=True,
            last_status="pending",
            next_check_at=now,
        )
        session.add(item)
        session.commit()

    monkeypatch.setattr(
        "snipebot.domain.price_checks.get_adapter", lambda site_key: _SuccessAdapter()
    )
    settings = get_settings()

    with session_factory() as session:
        processed = run_due_price_checks(session, settings)
    assert processed == 1

    with session_factory() as session:
        item = session.query(WatchItem).one()
        checks = session.query(PriceCheck).all()

    assert item.last_status == "ok"
    assert item.current_price == Decimal("19.99")
    assert item.last_checked_at is not None
    assert len(checks) == 1
    assert checks[0].status == "ok"
    assert checks[0].current_price == Decimal("19.99")
    assert checks[0].title == "Desk lamp"
    assert checks[0].currency == "EUR"


def test_failed_check_keeps_latest_price_and_stores_failure_history(
    monkeypatch,
) -> None:
    _reset_tables()
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    with session_factory() as session:
        item = WatchItem(
            owner_id="local",
            url="https://www.hema.nl/product/1",
            normalized_url="https://www.hema.nl/product/1",
            site_key="hema",
            active=True,
            last_status="pending",
            next_check_at=now,
        )
        session.add(item)
        session.commit()

    settings = get_settings()

    monkeypatch.setattr(
        "snipebot.domain.price_checks.get_adapter", lambda site_key: _SuccessAdapter()
    )
    with session_factory() as session:
        run_due_price_checks(session, settings)

    monkeypatch.setattr(
        "snipebot.domain.price_checks.get_adapter",
        lambda site_key: _ParseErrorAdapter(),
    )
    with session_factory() as session:
        item = session.query(WatchItem).one()
        item.next_check_at = datetime.now(UTC)
        session.commit()

    with session_factory() as session:
        run_due_price_checks(session, settings)

    with session_factory() as session:
        item = session.query(WatchItem).one()
        checks = session.query(PriceCheck).order_by(PriceCheck.id.asc()).all()

    assert item.current_price == Decimal("19.99")
    assert item.last_status == "parse_error"
    assert len(checks) == 2
    assert checks[0].status == "ok"
    assert checks[1].status == "parse_error"
    assert checks[1].error_kind == "parse_error"


def test_alerts_are_recorded_and_deduplicated_for_unchanged_state(monkeypatch) -> None:
    _reset_tables()
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    with session_factory() as session:
        item = WatchItem(
            owner_id="local",
            url="https://www.hema.nl/product/1",
            normalized_url="https://www.hema.nl/product/1",
            custom_label="Desk lamp",
            site_key="hema",
            target_price=Decimal("20.00"),
            current_price=Decimal("25.00"),
            active=True,
            last_status="pending",
            next_check_at=now,
        )
        session.add(item)
        session.commit()

    monkeypatch.setattr(
        "snipebot.domain.price_checks.get_adapter", lambda site_key: _SuccessAdapter()
    )
    notifier = _CollectingNotifier()
    monkeypatch.setattr(
        "snipebot.domain.price_checks.build_notifier", lambda settings: notifier
    )

    settings = get_settings()
    settings.notifications_enabled = True
    settings.telegram_enabled = True
    settings.telegram_bot_token = "token"
    settings.telegram_chat_id = "chat"

    with session_factory() as session:
        run_due_price_checks(session, settings)

    with session_factory() as session:
        first_run_alert_count = session.query(AlertEvent).count()

    with session_factory() as session:
        item = session.query(WatchItem).one()
        item.next_check_at = datetime.now(UTC)
        session.commit()

    with session_factory() as session:
        run_due_price_checks(session, settings)

    with session_factory() as session:
        alerts = session.query(AlertEvent).order_by(AlertEvent.id.asc()).all()

    assert first_run_alert_count == 2
    assert len(alerts) == 2
    assert alerts[0].alert_kind == "price_drop"
    assert alerts[1].alert_kind == "target_reached"
    assert all(alert.delivery_status == "sent" for alert in alerts)
    assert len(notifier.sent_messages) == 2
    assert "Desk lamp [hema]" in notifier.sent_messages[0]
    assert "Old: €25.00 → New: €19.99" in notifier.sent_messages[0]
    assert "https://www.hema.nl/product/1" in notifier.sent_messages[0]
