import logging
import time

from snipebot.core.config import get_settings
from snipebot.persistence.db import check_db_ready, init_db

logger = logging.getLogger(__name__)


def run_worker_loop() -> None:
    settings = get_settings()
    init_db()
    logger.info("worker started; interval=%s seconds", settings.worker_interval_seconds)

    while True:
        ready = check_db_ready()
        logger.info("worker tick: db_ready=%s", ready)
        time.sleep(settings.worker_interval_seconds)
