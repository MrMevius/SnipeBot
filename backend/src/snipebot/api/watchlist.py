from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.domain.services import (
    deactivate_watch_item,
    list_watch_items,
    upsert_watch_item,
)
from snipebot.persistence.db import get_db_session
from snipebot.persistence.models import WatchItem

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchItemCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    custom_label: str | None = Field(default=None, max_length=255)
    target_price: Decimal | None = Field(default=None, gt=0)


class WatchItemResponse(BaseModel):
    id: int
    url: str
    custom_label: str | None
    target_price: float | None
    site_key: str
    active: bool
    current_price: float | None
    last_checked_at: datetime | None
    last_status: str


class WatchlistResponse(BaseModel):
    items: list[WatchItemResponse]


class UpsertWatchItemResponse(BaseModel):
    operation: str
    item: WatchItemResponse


def _money_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_response(item: WatchItem) -> WatchItemResponse:
    return WatchItemResponse(
        id=item.id,
        url=item.url,
        custom_label=item.custom_label,
        target_price=_money_to_float(item.target_price),
        site_key=item.site_key,
        active=item.active,
        current_price=_money_to_float(item.current_price),
        last_checked_at=item.last_checked_at,
        last_status=item.last_status,
    )


@router.post("", response_model=UpsertWatchItemResponse)
def create_or_update_watch_item(
    payload: WatchItemCreateRequest,
    db_session: Session = Depends(get_db_session),
) -> UpsertWatchItemResponse:
    try:
        item, operation = upsert_watch_item(
            db_session,
            owner_id="local",
            url=payload.url,
            custom_label=payload.custom_label,
            target_price=payload.target_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return UpsertWatchItemResponse(operation=operation, item=_to_response(item))


@router.get("", response_model=WatchlistResponse)
def get_watchlist(db_session: Session = Depends(get_db_session)) -> WatchlistResponse:
    items = list_watch_items(db_session, owner_id="local")
    return WatchlistResponse(items=[_to_response(item) for item in items])


@router.patch("/{item_id}/deactivate", response_model=WatchItemResponse)
def deactivate_item(
    item_id: int, db_session: Session = Depends(get_db_session)
) -> WatchItemResponse:
    item = deactivate_watch_item(db_session, owner_id="local", item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)
