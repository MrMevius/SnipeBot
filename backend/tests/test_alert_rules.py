from decimal import Decimal

from snipebot.domain.alerts import decide_alerts


def test_decide_alerts_price_drop_only() -> None:
    intents = decide_alerts(
        previous_successful_price=Decimal("20.00"),
        new_price=Decimal("19.50"),
        target_price=Decimal("18.00"),
    )

    assert len(intents) == 1
    assert intents[0].kind == "price_drop"


def test_decide_alerts_target_reached_transition() -> None:
    intents = decide_alerts(
        previous_successful_price=Decimal("21.00"),
        new_price=Decimal("20.00"),
        target_price=Decimal("20.00"),
    )

    kinds = [intent.kind for intent in intents]
    assert "target_reached" in kinds
    assert "price_drop" in kinds


def test_decide_alerts_no_duplicate_when_still_below_target() -> None:
    intents = decide_alerts(
        previous_successful_price=Decimal("19.00"),
        new_price=Decimal("18.50"),
        target_price=Decimal("20.00"),
    )

    kinds = [intent.kind for intent in intents]
    assert "price_drop" in kinds
    assert "target_reached" not in kinds
