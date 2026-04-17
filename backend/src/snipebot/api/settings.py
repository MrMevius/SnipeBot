from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.core.config import get_settings as get_runtime_settings
from snipebot.domain.settings import (
    BackendSettings,
    get_backend_settings,
    is_bot_chat_id,
    update_backend_settings,
)
from snipebot.notifications.factory import build_notifier
from snipebot.notifications.models import NotificationMessage
from snipebot.persistence.db import get_db_session

router = APIRouter(prefix="/settings", tags=["settings"])


class BackendSettingsResponse(BaseModel):
    notifications_enabled: bool
    telegram_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    check_interval_seconds: int
    playwright_fallback_enabled: bool
    playwright_fallback_adapters: list[str]
    log_level: str


class BackendSettingsUpdateRequest(BaseModel):
    notifications_enabled: bool | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    check_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    playwright_fallback_enabled: bool | None = None
    playwright_fallback_adapters: list[str] | None = None
    log_level: str | None = None


class TelegramTestRequest(BaseModel):
    notifications_enabled: bool | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class TelegramTestResponse(BaseModel):
    ok: bool
    detail: str
    provider_message_id: str | None = None


def _to_response(payload: BackendSettings) -> BackendSettingsResponse:
    return BackendSettingsResponse(
        notifications_enabled=payload.notifications_enabled,
        telegram_enabled=payload.telegram_enabled,
        telegram_bot_token=payload.telegram_bot_token,
        telegram_chat_id=payload.telegram_chat_id,
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
            telegram_bot_token=payload.telegram_bot_token,
            telegram_chat_id=payload.telegram_chat_id,
            check_interval_seconds=payload.check_interval_seconds,
            playwright_fallback_enabled=payload.playwright_fallback_enabled,
            playwright_fallback_adapters=payload.playwright_fallback_adapters,
            log_level=payload.log_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(updated)


@router.post("/test-telegram", response_model=TelegramTestResponse)
def test_telegram_settings(
    payload: TelegramTestRequest,
    db_session: Session = Depends(get_db_session),
) -> TelegramTestResponse:
    resolved = get_backend_settings(db_session)
    runtime_settings = get_runtime_settings()

    notifications_enabled = (
        resolved.notifications_enabled
        if payload.notifications_enabled is None
        else payload.notifications_enabled
    )
    telegram_enabled = (
        resolved.telegram_enabled
        if payload.telegram_enabled is None
        else payload.telegram_enabled
    )
    telegram_bot_token = (
        resolved.telegram_bot_token
        if payload.telegram_bot_token is None
        else payload.telegram_bot_token.strip()
    )
    telegram_chat_id = (
        resolved.telegram_chat_id
        if payload.telegram_chat_id is None
        else payload.telegram_chat_id.strip()
    )

    if is_bot_chat_id(telegram_bot_token, telegram_chat_id):
        return TelegramTestResponse(
            ok=False,
            detail="telegram_chat_id may not be the bot id; use a user/group/channel chat id",
        )

    notifier = build_notifier(
        runtime_settings,
        notifications_enabled=notifications_enabled,
        telegram_enabled=telegram_enabled,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
    )
    result = notifier.send(
        NotificationMessage(
            title="🧪 SnipeBot test",
            body="Dit is een testbericht vanuit Settings.",
        )
    )
    if not result.ok:
        return TelegramTestResponse(
            ok=False,
            detail=result.error or "telegram_test_failed",
        )

    return TelegramTestResponse(
        ok=True,
        detail="Telegram testbericht succesvol verzonden.",
        provider_message_id=result.provider_message_id,
    )
