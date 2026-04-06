from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import detect_site_key, get_adapter
from snipebot.core.config import get_settings
from snipebot.domain.services import (
    deactivate_watch_item,
    get_watch_item_price_history,
    list_watch_items,
    normalize_product_url,
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


class WatchItemPreviewResponse(BaseModel):
    normalized_url: str
    site_key: str
    title: str
    current_price: float
    currency: str
    availability: str
    suggested_label: str


class WatchItemHistoryPointResponse(BaseModel):
    checked_at: datetime
    price: float


class WatchItemHistoryResponse(BaseModel):
    item_id: int
    site_key: str
    checks_count: int
    latest_price: float | None
    lowest_price: float | None
    highest_price: float | None
    series: list[WatchItemHistoryPointResponse]


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


@router.get("/preview", response_model=WatchItemPreviewResponse)
def preview_watch_item_url(
    url: str = Query(min_length=1, max_length=2048),
) -> WatchItemPreviewResponse:
    try:
        normalized_url = normalize_product_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    settings = get_settings()
    site_key = detect_site_key(normalized_url)
    adapter = get_adapter(site_key)
    if adapter is None:
        raise HTTPException(status_code=422, detail=f"Unsupported site: {site_key}")

    fallback_allowed = settings.playwright_fallback_enabled and adapter.site_key in {
        key.strip()
        for key in settings.playwright_fallback_adapters.split(",")
        if key.strip()
    }
    result = adapter.check(normalized_url, allow_playwright_fallback=fallback_allowed)

    if not result.ok or result.data is None:
        reason = result.error_message or result.error_kind or result.status
        raise HTTPException(status_code=422, detail=f"Preview failed: {reason}")

    return WatchItemPreviewResponse(
        normalized_url=normalized_url,
        site_key=site_key,
        title=result.data.title,
        current_price=float(result.data.current_price),
        currency=result.data.currency,
        availability=result.data.availability,
        suggested_label=result.data.title,
    )


@router.get("/{item_id}/history", response_model=WatchItemHistoryResponse)
def get_watch_item_history(
    item_id: int,
    days: int = 30,
    db_session: Session = Depends(get_db_session),
) -> WatchItemHistoryResponse:
    item, checks = get_watch_item_price_history(
        db_session,
        owner_id="local",
        item_id=item_id,
        days=days,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")

    prices = [
        float(check.current_price)
        for check in checks
        if check.current_price is not None
    ]
    latest_price = prices[-1] if prices else None
    lowest_price = min(prices) if prices else None
    highest_price = max(prices) if prices else None

    return WatchItemHistoryResponse(
        item_id=item.id,
        site_key=item.site_key,
        checks_count=len(prices),
        latest_price=latest_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        series=[
            WatchItemHistoryPointResponse(
                checked_at=check.checked_at,
                price=float(check.current_price),
            )
            for check in checks
            if check.current_price is not None
        ],
    )
