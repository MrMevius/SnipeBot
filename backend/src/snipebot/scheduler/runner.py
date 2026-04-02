import logging
import time

from snipebot.core.config import get_settings
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
        if ready:
            with session_factory() as db_session:
                processed = run_due_price_checks(db_session, settings)
        logger.info("worker tick: db_ready=%s processed=%s", ready, processed)
        time.sleep(settings.worker_interval_seconds)
