import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from snipebot.api.deps import (
    RequestIdentity,
    enforce_write_rate_limit,
    get_request_identity,
)
from snipebot.core.config import get_settings
from snipebot.core.metrics import metrics
from snipebot.domain.marketplace_archive import (
    ArchiveStore,
    archive_usage,
    build_store,
    cover_images,
    delete_archive_item,
    get_archive_image,
    get_archive_item,
    item_searches,
    list_archive_items,
    refresh_archive_item,
    version_changes,
)
from snipebot.persistence.db import get_db_session
from snipebot.persistence.models import MarketplaceItem

router = APIRouter(prefix="/archive", tags=["archive"])


def get_archive_store() -> ArchiveStore:
    return build_store(get_settings())


class ArchiveSearchRef(BaseModel):
    id: int
    name: str


class ArchiveItemSummary(BaseModel):
    id: int
    item_id: str
    title: str
    url: str
    price: float | None
    price_type: str | None
    status: str
    city: str | None
    cover_image_id: int | None
    thumbnail_url: str | None
    attributes: dict[str, str]
    first_seen_at: datetime
    last_seen_at: datetime
    gone_at: datetime | None
    archived_at: datetime | None
    searches: list[ArchiveSearchRef]


class ArchiveUsageResponse(BaseModel):
    items: int
    images: int
    bytes: int


class ArchiveListResponse(BaseModel):
    items: list[ArchiveItemSummary]
    total: int
    limit: int
    offset: int
    usage: ArchiveUsageResponse


class ArchiveImageResponse(BaseModel):
    id: int
    position: int
    first_seen_at: datetime
    removed_at: datetime | None


class ArchivePricePoint(BaseModel):
    price: float
    observed_at: datetime


class ArchiveFieldChange(BaseModel):
    label: str
    before: str | None
    after: str | None


class ArchiveVersionResponse(BaseModel):
    id: int
    fetched_at: datetime
    fields: list[ArchiveFieldChange]
    description_diff: list[str]
    images_added: int
    images_removed: int


class ArchiveItemDetail(ArchiveItemSummary):
    postcode: str | None
    category: list[str]
    description_html: str | None
    attribute_groups: list[dict[str, Any]]
    seller: dict[str, Any]
    stats: dict[str, Any]
    highlights: list[str]
    is_reserved: bool
    images: list[ArchiveImageResponse]
    price_history: list[ArchivePricePoint]
    versions: list[ArchiveVersionResponse]
    next_fetch_at: datetime | None
    fetch_failure_count: int
    last_error_message: str | None


def _summary_fields(
    item: MarketplaceItem, cover_image_id: int | None, searches: list[tuple[int, str]]
) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_id": item.item_id,
        "title": item.title,
        "url": item.url,
        "price": float(item.price) if item.price is not None else None,
        "price_type": item.price_type,
        "status": item.status,
        "city": item.city,
        "cover_image_id": cover_image_id,
        "thumbnail_url": item.thumbnail_url,
        "attributes": json.loads(item.summary_attributes_json or "{}"),
        "first_seen_at": item.first_seen_at,
        "last_seen_at": item.last_seen_at,
        "gone_at": item.gone_at,
        "archived_at": item.archived_at,
        "searches": [ArchiveSearchRef(id=search_id, name=name) for search_id, name in searches],
    }


def _get_owned_item(
    db_session: Session, identity: RequestIdentity, archive_id: int
) -> MarketplaceItem:
    item = get_archive_item(db_session, owner_id=identity.owner_id, archive_id=archive_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Archived listing not found")
    return item


def _detail_response(
    db_session: Session, identity: RequestIdentity, item: MarketplaceItem
) -> ArchiveItemDetail:
    searches = item_searches(db_session, owner_id=identity.owner_id, item_ids=[item.item_id])
    current_images = [image for image in item.images if image.removed_at is None]
    versions: list[ArchiveVersionResponse] = []
    previous: dict[str, Any] | None = None
    for version in item.versions:
        snapshot = json.loads(version.snapshot_json)
        changes = version_changes(previous, snapshot)
        versions.append(
            ArchiveVersionResponse(
                id=version.id,
                fetched_at=version.fetched_at,
                fields=[ArchiveFieldChange(**change) for change in changes["fields"]],
                description_diff=changes["description_diff"],
                images_added=changes["images_added"],
                images_removed=changes["images_removed"],
            )
        )
        previous = snapshot
    return ArchiveItemDetail(
        **_summary_fields(
            item,
            current_images[0].id if current_images else None,
            searches.get(item.item_id, []),
        ),
        postcode=item.postcode,
        category=json.loads(item.category_json or "[]"),
        description_html=item.description_html,
        attribute_groups=json.loads(item.attribute_groups_json or "[]"),
        seller=json.loads(item.seller_json or "{}"),
        stats=json.loads(item.stats_json or "{}"),
        highlights=json.loads(item.highlights_json or "[]"),
        is_reserved=item.is_reserved,
        images=[
            ArchiveImageResponse(
                id=image.id,
                position=image.position,
                first_seen_at=image.first_seen_at,
                removed_at=image.removed_at,
            )
            for image in sorted(
                item.images, key=lambda image: (image.removed_at is not None, image.position)
            )
        ],
        price_history=[
            ArchivePricePoint(price=float(point.price), observed_at=point.observed_at)
            for point in item.prices
        ],
        versions=list(reversed(versions)),
        next_fetch_at=item.next_fetch_at,
        fetch_failure_count=item.fetch_failure_count,
        last_error_message=item.last_error_message,
    )


@router.get("", response_model=ArchiveListResponse)
def get_archive(
    q: str | None = Query(default=None, max_length=200),
    search_id: int | None = None,
    status: Literal["online", "gone"] | None = None,
    sort: Literal["first_seen", "last_seen", "price", "title"] = "first_seen",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> ArchiveListResponse:
    items, total = list_archive_items(
        db_session,
        owner_id=identity.owner_id,
        q=q,
        search_id=search_id,
        status=status,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    covers = cover_images(db_session, [item.id for item in items])
    searches = item_searches(
        db_session, owner_id=identity.owner_id, item_ids=[item.item_id for item in items]
    )
    usage = archive_usage(db_session, owner_id=identity.owner_id)
    return ArchiveListResponse(
        items=[
            ArchiveItemSummary(
                **_summary_fields(item, covers.get(item.id), searches.get(item.item_id, []))
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
        usage=ArchiveUsageResponse(items=usage.items, images=usage.images, bytes=usage.bytes),
    )


@router.get("/images/{image_id}")
def get_image(
    image_id: int,
    db_session: Session = Depends(get_db_session),
    store: ArchiveStore = Depends(get_archive_store),
) -> FileResponse:
    # Plain <img> requests carry no owner header; photos are content-addressed.
    image = get_archive_image(db_session, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        path = store.path(image.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/{archive_id}", response_model=ArchiveItemDetail)
def get_archive_detail(
    archive_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> ArchiveItemDetail:
    return _detail_response(
        db_session, identity, _get_owned_item(db_session, identity, archive_id)
    )


@router.post("/{archive_id}/refresh", response_model=ArchiveItemDetail)
def refresh_item(
    archive_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> ArchiveItemDetail:
    enforce_write_rate_limit(request, identity)
    item = refresh_archive_item(db_session, _get_owned_item(db_session, identity, archive_id))
    return _detail_response(db_session, identity, item)


@router.delete("/{archive_id}", status_code=204)
def remove_item(
    archive_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
    store: ArchiveStore = Depends(get_archive_store),
) -> Response:
    enforce_write_rate_limit(request, identity)
    metrics.inc("api.archive.delete")
    delete_archive_item(db_session, _get_owned_item(db_session, identity, archive_id), store)
    return Response(status_code=204)
