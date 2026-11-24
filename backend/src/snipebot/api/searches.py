import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces.marktplaats import (
    Listing,
    MarktplaatsClient,
    MarktplaatsError,
)
from snipebot.api.deps import (
    RequestIdentity,
    enforce_write_rate_limit,
    get_request_identity,
)
from snipebot.core.metrics import metrics
from snipebot.domain.marketplace_archive import archive_ids_for
from snipebot.domain.marketplace_searches import (
    cheapest_listing,
    create_search,
    delete_search,
    get_exclude_keywords,
    get_search,
    get_search_description,
    is_listing_new,
    list_search_listings,
    list_searches,
    preview_search,
    search_listing_counts,
    trigger_search_check_now,
    update_search,
)
from snipebot.persistence.db import get_db_session
from snipebot.persistence.models import MarketplaceListing, MarketplaceSearch

router = APIRouter(prefix="/searches", tags=["searches"])

SellerType = Literal["all", "private", "business"]


def get_marktplaats_client() -> MarktplaatsClient:
    return MarktplaatsClient()


class SearchPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    seller_type: SellerType = "all"


class ListingSampleResponse(BaseModel):
    item_id: str
    title: str
    url: str
    image_url: str | None
    price: float | None
    price_type: str | None
    city: str | None


class SearchPreviewResponse(BaseModel):
    description: list[str]
    warnings: list[str]
    total_count: int
    sample: list[ListingSampleResponse]


class SearchCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=4096)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    seller_type: SellerType = "all"
    alert_max_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class SearchUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    exclude_keywords: list[str] | None = Field(default=None, max_length=50)
    seller_type: SellerType | None = None
    active: bool | None = None
    # null clears the ceiling (no alerts); omit the field to keep it.
    alert_max_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class CheapestListingResponse(BaseModel):
    item_id: str
    title: str
    url: str
    price: float
    archive_id: int | None


class SearchResponse(BaseModel):
    id: int
    marketplace: str
    name: str
    source_url: str
    description: list[str]
    exclude_keywords: list[str]
    seller_type: str
    alert_max_price: float | None
    active: bool
    baseline_done: bool
    last_checked_at: datetime | None
    next_check_at: datetime | None
    last_status: str
    last_error_message: str | None
    last_total_count: int | None
    listing_count: int
    new_listing_count: int
    cheapest: CheapestListingResponse | None
    created_at: datetime


class SearchListResponse(BaseModel):
    items: list[SearchResponse]


class ListingPricePointResponse(BaseModel):
    price: float
    observed_at: datetime


class ListingResponse(BaseModel):
    id: int
    item_id: str
    title: str
    url: str
    image_url: str | None
    price_type: str | None
    first_price: float | None
    current_price: float | None
    city: str | None
    distance_km: int | None
    seller_type: str | None
    attributes: dict[str, str]
    is_new: bool
    first_seen_at: datetime
    last_seen_at: datetime
    gone_at: datetime | None
    price_history: list[ListingPricePointResponse]
    archive_id: int | None = None


class ListingListResponse(BaseModel):
    search_id: int
    items: list[ListingResponse]


def _raise_for_marktplaats(exc: MarktplaatsError) -> None:
    status = 422 if exc.kind == "invalid_url" else 502
    raise HTTPException(status_code=status, detail=str(exc)) from exc


def _cheapest_response(
    db_session: Session, search: MarketplaceSearch
) -> CheapestListingResponse | None:
    row = cheapest_listing(db_session, search)
    if row is None or row.current_price is None:
        return None
    archive_ids = archive_ids_for(db_session, owner_id=search.owner_id, item_ids=[row.item_id])
    return CheapestListingResponse(
        item_id=row.item_id,
        title=row.title,
        url=row.url,
        price=float(row.current_price),
        archive_id=archive_ids.get(row.item_id),
    )


def _to_response(db_session: Session, search: MarketplaceSearch) -> SearchResponse:
    listing_count, new_count = search_listing_counts(db_session, search)
    return SearchResponse(
        id=search.id,
        marketplace=search.marketplace,
        name=search.name,
        source_url=search.source_url,
        description=get_search_description(search),
        exclude_keywords=get_exclude_keywords(search),
        seller_type=search.seller_type,
        alert_max_price=float(search.alert_max_price)
        if search.alert_max_price is not None
        else None,
        active=search.active,
        baseline_done=search.baseline_done,
        last_checked_at=search.last_checked_at,
        next_check_at=search.next_check_at,
        last_status=search.last_status,
        last_error_message=search.last_error_message,
        last_total_count=search.last_total_count,
        listing_count=listing_count,
        new_listing_count=new_count,
        cheapest=_cheapest_response(db_session, search),
        created_at=search.created_at,
    )


def _sample_response(listing: Listing) -> ListingSampleResponse:
    return ListingSampleResponse(
        item_id=listing.item_id,
        title=listing.title,
        url=listing.url,
        image_url=listing.image_url,
        price=float(listing.price) if listing.price is not None else None,
        price_type=listing.price_type,
        city=listing.city,
    )


def _listing_response(
    row: MarketplaceListing, now: datetime, archive_id: int | None = None
) -> ListingResponse:
    return ListingResponse(
        id=row.id,
        item_id=row.item_id,
        title=row.title,
        url=row.url,
        image_url=row.image_url,
        price_type=row.price_type,
        first_price=float(row.first_price) if row.first_price is not None else None,
        current_price=float(row.current_price) if row.current_price is not None else None,
        city=row.city,
        distance_km=round(row.distance_meters / 1000)
        if row.distance_meters is not None
        else None,
        seller_type=row.seller_type,
        attributes=json.loads(row.attributes_json or "{}"),
        is_new=is_listing_new(row, now),
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        gone_at=row.gone_at,
        price_history=[
            ListingPricePointResponse(price=float(point.price), observed_at=point.observed_at)
            for point in row.prices
        ],
        archive_id=archive_id,
    )


def _get_owned_search(
    db_session: Session, identity: RequestIdentity, search_id: int
) -> MarketplaceSearch:
    search = get_search(db_session, owner_id=identity.owner_id, search_id=search_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.post("/preview", response_model=SearchPreviewResponse)
def preview(
    payload: SearchPreviewRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    client: MarktplaatsClient = Depends(get_marktplaats_client),
) -> SearchPreviewResponse:
    enforce_write_rate_limit(request, identity)
    metrics.inc("api.searches.preview")
    try:
        result = preview_search(client, url=payload.url, seller_type=payload.seller_type)
    except MarktplaatsError as exc:
        _raise_for_marktplaats(exc)
    return SearchPreviewResponse(
        description=result.description,
        warnings=result.warnings,
        total_count=result.total_count,
        sample=[_sample_response(listing) for listing in result.sample],
    )


@router.get("", response_model=SearchListResponse)
def get_searches(
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> SearchListResponse:
    searches = list_searches(db_session, owner_id=identity.owner_id)
    return SearchListResponse(items=[_to_response(db_session, item) for item in searches])


@router.post("", response_model=SearchResponse, status_code=201)
def post_search(
    payload: SearchCreateRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
    client: MarktplaatsClient = Depends(get_marktplaats_client),
) -> SearchResponse:
    enforce_write_rate_limit(request, identity)
    metrics.inc("api.searches.create")
    try:
        search = create_search(
            db_session,
            client,
            owner_id=identity.owner_id,
            name=payload.name,
            url=payload.url,
            exclude_keywords=payload.exclude_keywords,
            seller_type=payload.seller_type,
            alert_max_price=payload.alert_max_price,
        )
    except MarktplaatsError as exc:
        _raise_for_marktplaats(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(db_session, search)


@router.get("/{search_id}", response_model=SearchResponse)
def get_search_detail(
    search_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> SearchResponse:
    return _to_response(db_session, _get_owned_search(db_session, identity, search_id))


@router.patch("/{search_id}", response_model=SearchResponse)
def patch_search(
    search_id: int,
    payload: SearchUpdateRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
    client: MarktplaatsClient = Depends(get_marktplaats_client),
) -> SearchResponse:
    enforce_write_rate_limit(request, identity)
    search = _get_owned_search(db_session, identity, search_id)
    try:
        search = update_search(
            db_session,
            client,
            search,
            name=payload.name,
            exclude_keywords=payload.exclude_keywords,
            seller_type=payload.seller_type,
            active=payload.active,
            **(
                {"alert_max_price": payload.alert_max_price}
                if "alert_max_price" in payload.model_fields_set
                else {}
            ),
        )
    except MarktplaatsError as exc:
        _raise_for_marktplaats(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(db_session, search)


@router.delete("/{search_id}", status_code=204)
def remove_search(
    search_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> Response:
    enforce_write_rate_limit(request, identity)
    delete_search(db_session, _get_owned_search(db_session, identity, search_id))
    return Response(status_code=204)


@router.post("/{search_id}/check-now", response_model=SearchResponse)
def check_now(
    search_id: int,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> SearchResponse:
    enforce_write_rate_limit(request, identity)
    search = trigger_search_check_now(
        db_session, _get_owned_search(db_session, identity, search_id)
    )
    return _to_response(db_session, search)


@router.get("/{search_id}/listings", response_model=ListingListResponse)
def get_listings(
    search_id: int,
    identity: RequestIdentity = Depends(get_request_identity),
    db_session: Session = Depends(get_db_session),
) -> ListingListResponse:
    search = _get_owned_search(db_session, identity, search_id)
    now = datetime.now(UTC)
    rows = list_search_listings(db_session, search)
    archive_ids = archive_ids_for(
        db_session, owner_id=identity.owner_id, item_ids=[row.item_id for row in rows]
    )
    return ListingListResponse(
        search_id=search.id,
        items=[_listing_response(row, now, archive_ids.get(row.item_id)) for row in rows],
    )
