from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.domain.settings import (
    BackendSettings,
    get_backend_settings,
    update_backend_settings,
)
from snipebot.persistence.db import get_db_session

router = APIRouter(prefix="/settings", tags=["settings"])


class BackendSettingsResponse(BaseModel):
    notifications_enabled: bool
    telegram_enabled: bool
    check_interval_seconds: int
    playwright_fallback_enabled: bool
    playwright_fallback_adapters: list[str]
    log_level: str


class BackendSettingsUpdateRequest(BaseModel):
    notifications_enabled: bool | None = None
    telegram_enabled: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    playwright_fallback_enabled: bool | None = None
    playwright_fallback_adapters: list[str] | None = None
    log_level: str | None = None


def _to_response(payload: BackendSettings) -> BackendSettingsResponse:
    return BackendSettingsResponse(
        notifications_enabled=payload.notifications_enabled,
        telegram_enabled=payload.telegram_enabled,
        check_interval_seconds=payload.check_interval_seconds,
        playwright_fallback_enabled=payload.playwright_fallback_enabled,
        playwright_fallback_adapters=payload.playwright_fallback_adapters,
        log_level=payload.log_level,
    )


@router.get("", response_model=BackendSettingsResponse)
def get_settings(
    db_session: Session = Depends(get_db_session),
) -> BackendSettingsResponse:
    return _to_response(get_backend_settings(db_session))


@router.patch("", response_model=BackendSettingsResponse)
def patch_settings(
    payload: BackendSettingsUpdateRequest,
    db_session: Session = Depends(get_db_session),
) -> BackendSettingsResponse:
    try:
        updated = update_backend_settings(
            db_session,
            notifications_enabled=payload.notifications_enabled,
            telegram_enabled=payload.telegram_enabled,
            check_interval_seconds=payload.check_interval_seconds,
            playwright_fallback_enabled=payload.playwright_fallback_enabled,
            playwright_fallback_adapters=payload.playwright_fallback_adapters,
            log_level=payload.log_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(updated)
