from snipebot.persistence.db import check_db_ready, init_db


def test_db_ready_after_init() -> None:
    init_db()
    assert check_db_ready() is True
