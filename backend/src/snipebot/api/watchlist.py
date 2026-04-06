from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.adapters.sites.registry import detect_site_key, get_adapter
from snipebot.core.config import get_settings
from snipebot.domain.services import (
    archive_watch_item,
    bulk_update_watch_items,
    restore_watch_item,
    get_watch_item_lows,
    deactivate_watch_item,
    get_watch_item_price_history,
    list_watch_item_alert_events,
    list_watch_items_paginated,
    normalize_product_url,
    trigger_watch_item_check_now,
    update_watch_item,
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
    notes: str | None
    target_price: float | None
    site_key: str
    active: bool
    current_price: float | None
    last_checked_at: datetime | None
    last_status: str
    archived_at: datetime | None


class WatchlistResponse(BaseModel):
    items: list[WatchItemResponse]
    total: int
    limit: int
    offset: int


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


class WatchItemUpdateRequest(BaseModel):
    custom_label: str | None = Field(default=None, max_length=255)
    target_price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class WatchItemLowSummaryResponse(BaseModel):
    low_7d: float | None
    low_30d: float | None
    all_time_low: float | None


class WatchItemDetailResponse(BaseModel):
    item: WatchItemResponse
    lows: WatchItemLowSummaryResponse


class CheckNowResponse(BaseModel):
    status: str
    item: WatchItemResponse


class AlertEventResponse(BaseModel):
    id: int
    alert_kind: str
    delivery_status: str
    sent_at: datetime
    old_price: float | None
    new_price: float
    target_price: float | None
    channel: str
    error_message: str | None


class AlertHistoryResponse(BaseModel):
    item_id: int
    events: list[AlertEventResponse]


class BulkWatchItemRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1)
    action: str
    target_price: Decimal | None = Field(default=None, gt=0)


class BulkWatchItemFailure(BaseModel):
    item_id: int
    reason: str


class BulkWatchItemResponse(BaseModel):
    action: str
    updated: int
    failed: list[BulkWatchItemFailure]


def _money_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_response(item: WatchItem) -> WatchItemResponse:
    return WatchItemResponse(
        id=item.id,
        url=item.url,
        custom_label=item.custom_label,
        notes=item.notes,
        target_price=_money_to_float(item.target_price),
        site_key=item.site_key,
        active=item.active,
        current_price=_money_to_float(item.current_price),
        last_checked_at=item.last_checked_at,
        last_status=item.last_status,
        archived_at=item.archived_at,
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
def get_watchlist(
    active: bool | None = None,
    site_key: str | None = Query(default=None, max_length=64),
    has_target: bool | None = None,
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="updated_desc", max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_archived: bool = False,
    archived_only: bool = False,
    db_session: Session = Depends(get_db_session),
) -> WatchlistResponse:
    items, total, safe_limit, safe_offset = list_watch_items_paginated(
        db_session,
        owner_id="local",
        active=active,
        site_key=site_key,
        has_target=has_target,
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        archived_only=archived_only,
    )
    return WatchlistResponse(
        items=[_to_response(item) for item in items],
        total=total,
        limit=safe_limit,
        offset=safe_offset,
    )


@router.post("/bulk", response_model=BulkWatchItemResponse)
def bulk_watch_items(
    payload: BulkWatchItemRequest,
    db_session: Session = Depends(get_db_session),
) -> BulkWatchItemResponse:
    if payload.action not in {"pause", "resume", "archive", "set_target"}:
        raise HTTPException(status_code=422, detail="Unsupported bulk action")

    if (
        payload.action == "set_target"
        and "target_price" not in payload.model_fields_set
    ):
        raise HTTPException(
            status_code=422,
            detail="target_price is required for set_target",
        )

    updated, failed = bulk_update_watch_items(
        db_session,
        owner_id="local",
        item_ids=payload.item_ids,
        action=payload.action,
        target_price=payload.target_price,
    )
    return BulkWatchItemResponse(
        action=payload.action,
        updated=updated,
        failed=[
            BulkWatchItemFailure(item_id=item_id, reason=reason)
            for item_id, reason in failed
        ],
    )


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


@router.get("/{item_id}", response_model=WatchItemDetailResponse)
def get_watch_item_detail(
    item_id: int,
    db_session: Session = Depends(get_db_session),
) -> WatchItemDetailResponse:
    item, low_7d, low_30d, all_time_low = get_watch_item_lows(
        db_session,
        owner_id="local",
        item_id=item_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")

    return WatchItemDetailResponse(
        item=_to_response(item),
        lows=WatchItemLowSummaryResponse(
            low_7d=low_7d,
            low_30d=low_30d,
            all_time_low=all_time_low,
        ),
    )


@router.patch("/{item_id}", response_model=WatchItemResponse)
def patch_watch_item(
    item_id: int,
    payload: WatchItemUpdateRequest,
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    update_fields = payload.model_fields_set
    item = update_watch_item(
        db_session,
        owner_id="local",
        item_id=item_id,
        custom_label=payload.custom_label,
        target_price=payload.target_price,
        notes=payload.notes,
        active=payload.active,
        set_custom_label="custom_label" in update_fields,
        set_target_price="target_price" in update_fields,
        set_notes="notes" in update_fields,
        set_active="active" in update_fields,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.post("/{item_id}/check-now", response_model=CheckNowResponse)
def check_now_watch_item(
    item_id: int,
    db_session: Session = Depends(get_db_session),
) -> CheckNowResponse:
    item = trigger_watch_item_check_now(db_session, owner_id="local", item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return CheckNowResponse(
        status="queued_for_next_worker_tick",
        item=_to_response(item),
    )


@router.get("/{item_id}/alerts", response_model=AlertHistoryResponse)
def get_watch_item_alert_history(
    item_id: int,
    limit: int = 25,
    db_session: Session = Depends(get_db_session),
) -> AlertHistoryResponse:
    item, events = list_watch_item_alert_events(
        db_session,
        owner_id="local",
        item_id=item_id,
        limit=limit,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")

    return AlertHistoryResponse(
        item_id=item.id,
        events=[
            AlertEventResponse(
                id=event.id,
                alert_kind=event.alert_kind,
                delivery_status=event.delivery_status,
                sent_at=event.sent_at,
                old_price=_money_to_float(event.old_price),
                new_price=float(event.new_price),
                target_price=_money_to_float(event.target_price),
                channel=event.channel,
                error_message=event.error_message,
            )
            for event in events
        ],
    )


@router.patch("/{item_id}/deactivate", response_model=WatchItemResponse)
def deactivate_item(
    item_id: int, db_session: Session = Depends(get_db_session)
) -> WatchItemResponse:
    item = deactivate_watch_item(db_session, owner_id="local", item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.post("/{item_id}/archive", response_model=WatchItemResponse)
def archive_item(
    item_id: int, db_session: Session = Depends(get_db_session)
) -> WatchItemResponse:
    item = archive_watch_item(db_session, owner_id="local", item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.post("/{item_id}/restore", response_model=WatchItemResponse)
def restore_item(
    item_id: int, db_session: Session = Depends(get_db_session)
) -> WatchItemResponse:
    item = restore_watch_item(db_session, owner_id="local", item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


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
