from datetime import datetime
from decimal import Decimal
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from snipebot.api.deps import (
    RequestIdentity,
    enforce_write_rate_limit,
    get_request_identity,
)
from snipebot.adapters.sites.registry import detect_site_key, get_adapter
from snipebot.core.config import get_settings
from snipebot.core.metrics import metrics
from snipebot.domain.services import (
    archive_watch_item,
    bulk_update_watch_items,
    export_watch_items_rows,
    get_or_create_watch_tag,
    restore_watch_item,
    import_watch_items_rows,
    get_watch_item_lows,
    get_watchlist_health_summary,
    deactivate_watch_item,
    get_watch_item_price_history,
    list_watch_item_alert_events,
    list_watch_items_paginated,
    list_watch_tags,
    normalize_product_url,
    set_watch_item_tags,
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
    consecutive_failure_count: int
    dead_lettered_at: datetime | None
    dead_letter_reason: str | None
    tags: list[str]


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


class WatchTagResponse(BaseModel):
    id: int
    name: str


class WatchTagListResponse(BaseModel):
    tags: list[WatchTagResponse]


class CreateWatchTagRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class SetWatchItemTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class ImportWatchlistRequest(BaseModel):
    items: list[dict[str, object]] = Field(default_factory=list)


class ImportWatchlistRowResult(BaseModel):
    row: int
    status: str
    url: str | None = None
    normalized_url: str | None = None
    error: str | None = None


class ImportWatchlistSummary(BaseModel):
    created: int
    updated: int
    error: int


class ImportWatchlistResponse(BaseModel):
    dry_run: bool
    summary: ImportWatchlistSummary
    rows: list[ImportWatchlistRowResult]


class WatchlistHealthResponse(BaseModel):
    owner_id: str
    total: int
    active: int
    archived: int
    stale: int
    error: int
    dead_lettered: int


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
        consecutive_failure_count=item.consecutive_failure_count,
        dead_lettered_at=item.dead_lettered_at,
        dead_letter_reason=item.dead_letter_reason,
        tags=[
            tag.name for tag in sorted(item.tags, key=lambda entry: entry.name.lower())
        ],
    )


def _resolve_owner(identity: RequestIdentity) -> str:
    return identity.owner_id


@router.post("", response_model=UpsertWatchItemResponse)
def create_or_update_watch_item(
    payload: WatchItemCreateRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> UpsertWatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.upsert")
    try:
        item, operation = upsert_watch_item(
            db_session,
            owner_id=owner_id,
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
    tag: str | None = Query(default=None, max_length=64),
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchlistResponse:
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.list")
    items, total, safe_limit, safe_offset = list_watch_items_paginated(
        db_session,
        owner_id=owner_id,
        active=active,
        site_key=site_key,
        has_target=has_target,
        query=q,
        sort=sort,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
        archived_only=archived_only,
        tag=tag,
    )
    return WatchlistResponse(
        items=[_to_response(item) for item in items],
        total=total,
        limit=safe_limit,
        offset=safe_offset,
    )


@router.get("/health", response_model=WatchlistHealthResponse)
def get_watchlist_health(
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchlistHealthResponse:
    owner_id = _resolve_owner(identity)
    settings = get_settings()
    summary = get_watchlist_health_summary(
        db_session,
        owner_id=owner_id,
        stale_after_seconds=settings.check_interval_seconds * 2,
    )
    metrics.inc("api.watchlist.health")
    return WatchlistHealthResponse(owner_id=owner_id, **summary)


@router.get("/tags", response_model=WatchTagListResponse)
def get_watchlist_tags(
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchTagListResponse:
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.tags_list")
    tags = list_watch_tags(db_session, owner_id=owner_id)
    return WatchTagListResponse(
        tags=[WatchTagResponse(id=tag.id, name=tag.name) for tag in tags]
    )


@router.post("/tags", response_model=WatchTagResponse)
def create_watchlist_tag(
    payload: CreateWatchTagRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchTagResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.tags_create")
    try:
        tag = get_or_create_watch_tag(db_session, owner_id=owner_id, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WatchTagResponse(id=tag.id, name=tag.name)


@router.patch("/{item_id}/tags", response_model=WatchItemResponse)
def patch_watch_item_tags(
    item_id: int,
    payload: SetWatchItemTagsRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.tags_patch")
    try:
        item = set_watch_item_tags(
            db_session,
            owner_id=owner_id,
            item_id=item_id,
            tag_names=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.get("/export")
def export_watchlist(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    active: bool | None = None,
    site_key: str | None = Query(default=None, max_length=64),
    has_target: bool | None = None,
    q: str | None = Query(default=None, max_length=255),
    sort: str = Query(default="updated_desc", max_length=32),
    include_archived: bool = False,
    archived_only: bool = False,
    tag: str | None = Query(default=None, max_length=64),
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
):
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.export")
    rows = export_watch_items_rows(
        db_session,
        owner_id=owner_id,
        active=active,
        site_key=site_key,
        has_target=has_target,
        query=q,
        sort=sort,
        include_archived=include_archived,
        archived_only=archived_only,
        tag=tag,
    )

    if format == "json":
        return JSONResponse(content={"items": rows, "count": len(rows)})

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "url",
            "custom_label",
            "target_price",
            "site_key",
            "active",
            "archived_at",
            "tags",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["url"],
                row["custom_label"],
                row["target_price"],
                row["site_key"],
                row["active"],
                row["archived_at"],
                ", ".join(row["tags"]),
            ]
        )
    output.seek(0)
    filename = f"watchlist-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportWatchlistResponse)
def import_watchlist(
    payload: ImportWatchlistRequest,
    request: Request,
    dry_run: bool = True,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> ImportWatchlistResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.import")
    row_results, summary = import_watch_items_rows(
        db_session,
        owner_id=owner_id,
        rows=payload.items,
        dry_run=dry_run,
    )

    return ImportWatchlistResponse(
        dry_run=dry_run,
        summary=ImportWatchlistSummary(
            created=summary["created"],
            updated=summary["updated"],
            error=summary["error"],
        ),
        rows=[
            ImportWatchlistRowResult(
                row=entry["row"],
                status=entry["status"],
                url=entry.get("url"),
                normalized_url=entry.get("normalized_url"),
                error=entry.get("error"),
            )
            for entry in row_results
        ],
    )


@router.post("/bulk", response_model=BulkWatchItemResponse)
def bulk_watch_items(
    payload: BulkWatchItemRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> BulkWatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.bulk")
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
        owner_id=owner_id,
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
    metrics.inc("api.watchlist.preview")
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
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemDetailResponse:
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.detail")
    item, low_7d, low_30d, all_time_low = get_watch_item_lows(
        db_session,
        owner_id=owner_id,
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
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.patch")
    update_fields = payload.model_fields_set
    item = update_watch_item(
        db_session,
        owner_id=owner_id,
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
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> CheckNowResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.check_now")
    item = trigger_watch_item_check_now(db_session, owner_id=owner_id, item_id=item_id)
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
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> AlertHistoryResponse:
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.alerts")
    item, events = list_watch_item_alert_events(
        db_session,
        owner_id=owner_id,
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
    item_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.deactivate")
    item = deactivate_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.post("/{item_id}/archive", response_model=WatchItemResponse)
def archive_item(
    item_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.archive")
    item = archive_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.post("/{item_id}/restore", response_model=WatchItemResponse)
def restore_item(
    item_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemResponse:
    enforce_write_rate_limit(request, identity)
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.restore")
    item = restore_watch_item(db_session, owner_id=owner_id, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Watch item not found")
    return _to_response(item)


@router.get("/{item_id}/history", response_model=WatchItemHistoryResponse)
def get_watch_item_history(
    item_id: int,
    days: int = 30,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> WatchItemHistoryResponse:
    owner_id = _resolve_owner(identity)
    metrics.inc("api.watchlist.history")
    item, checks = get_watch_item_price_history(
        db_session,
        owner_id=owner_id,
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
