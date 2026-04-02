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
    )


def _get_env(name: str, default: str) -> str:
    import os

    return os.getenv(name, default)
