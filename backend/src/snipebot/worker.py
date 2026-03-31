from snipebot.core.config import get_settings
from snipebot.core.logging import configure_logging
from snipebot.scheduler.runner import run_worker_loop


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    run_worker_loop()


if __name__ == "__main__":
    main()
