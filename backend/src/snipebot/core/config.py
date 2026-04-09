from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "development"
    log_level: str = "INFO"
    db_url: str = "sqlite:////data/snipebot.db"
    worker_interval_seconds: int = 60
    check_interval_seconds: int = 1800
    retry_interval_seconds: int = 300
    worker_batch_size: int = 25
    playwright_fallback_enabled: bool = False
    playwright_fallback_adapters: str = ""
    notifications_enabled: bool = False
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    auth_default_owner_id: str = "local"
    auth_header_name: str = "x-owner-id"
    rate_limit_write_requests_per_minute: int = 60
    rate_limit_window_seconds: int = 60
    dead_letter_failure_threshold: int = 5
    retry_backoff_multiplier: int = 2
    retry_max_interval_seconds: int = 3600

    @property
    def is_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        env=_get_env("SNIPEBOT_ENV", "development"),
        log_level=_get_env("SNIPEBOT_LOG_LEVEL", "INFO"),
        db_url=_get_env("SNIPEBOT_DB_URL", "sqlite:////data/snipebot.db"),
        worker_interval_seconds=int(_get_env("SNIPEBOT_WORKER_INTERVAL_SECONDS", "60")),
        check_interval_seconds=int(_get_env("SNIPEBOT_CHECK_INTERVAL_SECONDS", "1800")),
        retry_interval_seconds=int(_get_env("SNIPEBOT_RETRY_INTERVAL_SECONDS", "300")),
        worker_batch_size=int(_get_env("SNIPEBOT_WORKER_BATCH_SIZE", "25")),
        playwright_fallback_enabled=_get_env(
            "SNIPEBOT_PLAYWRIGHT_FALLBACK_ENABLED", "false"
        ).lower()
        in {"1", "true", "yes", "on"},
        playwright_fallback_adapters=_get_env(
            "SNIPEBOT_PLAYWRIGHT_FALLBACK_ADAPTERS", ""
        ),
        notifications_enabled=_get_env(
            "SNIPEBOT_NOTIFICATIONS_ENABLED", "false"
        ).lower()
        in {"1", "true", "yes", "on"},
        telegram_enabled=_get_env("SNIPEBOT_TELEGRAM_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        telegram_bot_token=_get_env("SNIPEBOT_TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=_get_env("SNIPEBOT_TELEGRAM_CHAT_ID", ""),
        auth_default_owner_id=_get_env("SNIPEBOT_AUTH_DEFAULT_OWNER_ID", "local"),
        auth_header_name=_get_env("SNIPEBOT_AUTH_HEADER_NAME", "x-owner-id"),
        rate_limit_write_requests_per_minute=int(
            _get_env("SNIPEBOT_RATE_LIMIT_WRITE_REQUESTS_PER_MINUTE", "60")
        ),
        rate_limit_window_seconds=int(
            _get_env("SNIPEBOT_RATE_LIMIT_WINDOW_SECONDS", "60")
        ),
        dead_letter_failure_threshold=int(
            _get_env("SNIPEBOT_DEAD_LETTER_FAILURE_THRESHOLD", "5")
        ),
        retry_backoff_multiplier=int(
            _get_env("SNIPEBOT_RETRY_BACKOFF_MULTIPLIER", "2")
        ),
        retry_max_interval_seconds=int(
            _get_env("SNIPEBOT_RETRY_MAX_INTERVAL_SECONDS", "3600")
        ),
    )


def _get_env(name: str, default: str) -> str:
    import os

    return os.getenv(name, default)
