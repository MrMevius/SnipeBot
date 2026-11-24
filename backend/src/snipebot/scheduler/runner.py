import logging
import time

from snipebot.core.config import get_settings
from snipebot.domain.marketplace_archive import run_due_archive_fetches
from snipebot.domain.marketplace_searches import run_due_marketplace_searches
from snipebot.domain.price_checks import run_due_price_checks
from snipebot.persistence.db import check_db_ready, init_db
from snipebot.persistence.db import get_session_factory

logger = logging.getLogger(__name__)


def run_worker_loop() -> None:
    settings = get_settings()
    init_db()
    logger.info("worker started; interval=%s seconds", settings.worker_interval_seconds)
    session_factory = get_session_factory()

    while True:
        ready = check_db_ready()
        processed = 0
        searches = 0
        archived = 0
        if ready:
            with session_factory() as db_session:
                processed = run_due_price_checks(db_session, settings)
            with session_factory() as db_session:
                searches = run_due_marketplace_searches(db_session, settings)
            try:
                with session_factory() as db_session:
                    archived = run_due_archive_fetches(db_session, settings)
            except Exception:  # pragma: no cover - keep price checks running
                logger.exception("marketplace archive tick failed")
        logger.info(
            "worker tick: db_ready=%s processed=%s marketplace_searches=%s archive_fetches=%s",
            ready,
            processed,
            searches,
            archived,
        )
        time.sleep(settings.worker_interval_seconds)
