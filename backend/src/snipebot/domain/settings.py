from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from snipebot.core.config import get_settings
from snipebot.persistence.models import AppSetting

ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
ALLOWED_HISTORY_DAYS = {7, 30, 90}
ALLOWED_CURRENCY_DISPLAY_MODES = {"symbol", "code"}


@dataclass
class BackendSettings:
    notifications_enabled: bool
    telegram_enabled: bool
    check_interval_seconds: int
    playwright_fallback_enabled: bool
    playwright_fallback_adapters: list[str]
    log_level: str


def get_backend_settings(db_session: Session) -> BackendSettings:
    defaults = get_settings()
    values = _load_settings_map(db_session)

    return BackendSettings(
        notifications_enabled=_as_bool(
            values.get("notifications_enabled"), defaults.notifications_enabled
        ),
        telegram_enabled=_as_bool(
            values.get("telegram_enabled"), defaults.telegram_enabled
        ),
        check_interval_seconds=_as_int(
            values.get("check_interval_seconds"), defaults.check_interval_seconds
        ),
        playwright_fallback_enabled=_as_bool(
            values.get("playwright_fallback_enabled"),
            defaults.playwright_fallback_enabled,
        ),
        playwright_fallback_adapters=_as_csv_list(
            values.get("playwright_fallback_adapters"),
            defaults.playwright_fallback_adapters,
        ),
        log_level=_as_log_level(values.get("log_level"), defaults.log_level),
    )


def update_backend_settings(
    db_session: Session,
    *,
    notifications_enabled: bool | None = None,
    telegram_enabled: bool | None = None,
    check_interval_seconds: int | None = None,
    playwright_fallback_enabled: bool | None = None,
    playwright_fallback_adapters: list[str] | None = None,
    log_level: str | None = None,
) -> BackendSettings:
    if notifications_enabled is not None:
        _set_setting(
            db_session, "notifications_enabled", _to_bool_str(notifications_enabled)
        )

    if telegram_enabled is not None:
        _set_setting(db_session, "telegram_enabled", _to_bool_str(telegram_enabled))

    if check_interval_seconds is not None:
        if check_interval_seconds < 30 or check_interval_seconds > 86400:
            raise ValueError("check_interval_seconds must be between 30 and 86400")
        _set_setting(db_session, "check_interval_seconds", str(check_interval_seconds))

    if playwright_fallback_enabled is not None:
        _set_setting(
            db_session,
            "playwright_fallback_enabled",
            _to_bool_str(playwright_fallback_enabled),
        )

    if playwright_fallback_adapters is not None:
        cleaned = sorted(
            {
                adapter.strip()
                for adapter in playwright_fallback_adapters
                if adapter.strip()
            }
        )
        _set_setting(db_session, "playwright_fallback_adapters", ",".join(cleaned))

    if log_level is not None:
        upper = log_level.upper()
        if upper not in ALLOWED_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of: {', '.join(sorted(ALLOWED_LOG_LEVELS))}"
            )
        _set_setting(db_session, "log_level", upper)

    db_session.commit()
    return get_backend_settings(db_session)


def _load_settings_map(db_session: Session) -> dict[str, str]:
    rows = db_session.scalars(select(AppSetting)).all()
    return {row.key: row.value for row in rows}


def _set_setting(db_session: Session, key: str, value: str) -> None:
    existing = db_session.get(AppSetting, key)
    if existing is None:
        db_session.add(AppSetting(key=key, value=value))
        return

    existing.value = value


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _as_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_csv_list(raw: str | None, default: str) -> list[str]:
    source = raw if raw is not None else default
    return [entry.strip() for entry in source.split(",") if entry.strip()]


def _as_log_level(raw: str | None, default: str) -> str:
    candidate = (raw if raw is not None else default).upper()
    if candidate not in ALLOWED_LOG_LEVELS:
        return "INFO"
    return candidate


def _to_bool_str(value: bool) -> str:
    return "true" if value else "false"
