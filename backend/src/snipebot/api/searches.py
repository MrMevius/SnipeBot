import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from snipebot.adapters.marketplaces.base import (
    Listing,
    MarketplaceError,
    PlatformAdapter,
    SearchFilters,
)
from snipebot.adapters.marketplaces.platforms import get_adapters, home_location, platform_label
from snipebot.api.deps import (
    RequestIdentity,
    enforce_write_rate_limit,
    get_request_identity,
)
from snipebot.core.metrics import metrics
from snipebot.domain.marketplace_archive import archive_ids_for
from snipebot.domain.marketplace_searches import (
    MergedOption,
    cheapest_listing,
    create_search,
    delete_search,
    earliest_listing,
    get_exclude_keywords,
    get_post_filters,
    get_search,
    get_search_description,
    get_search_filters,
    is_listing_new,
    list_makes,
    list_models,
    list_search_cars,
    list_searches,
    preview_search,
    search_listing_counts,
    search_status,
    trigger_search_check_now,
    update_search,
)
from snipebot.persistence.db import get_db_session
from snipebot.persistence.models import MarketplaceListing, MarketplaceSearch

router = APIRouter(prefix="/searches", tags=["searches"])

SellerType = Literal["all", "private", "business"]
UnknownPolicy = Literal["include", "quiet", "exclude"]
FilterValue = Annotated[int | None, Field(default=None, ge=0, le=100_000_000)]


def get_platform_adapters() -> dict[str, PlatformAdapter]:
    return get_adapters()


class FiltersModel(BaseModel):
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year_min: FilterValue = None
    year_max: FilterValue = None
    price_min: FilterValue = None
    price_max: FilterValue = None
    mileage_min: FilterValue = None
    mileage_max: FilterValue = None
    range_min: FilterValue = None
    battery_min: FilterValue = None
    battery_max: FilterValue = None
    variants: list[str] | None = Field(default=None, max_length=4)

    def to_filters(self) -> SearchFilters:
        return SearchFilters(**self.model_dump())


class PlatformResponse(BaseModel):
    key: str
    label: str


class PlatformListResponse(BaseModel):
    items: list[PlatformResponse]


class OptionResponse(BaseModel):
    label: str
    platforms: list[str]


class OptionListResponse(BaseModel):
    items: list[OptionResponse]
    warnings: list[str]


class SearchPreviewRequest(BaseModel):
    filters: FiltersModel
    platforms: list[str] = Field(min_length=1, max_length=10)
    seller_type: SellerType = "all"
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)


class ListingSampleResponse(BaseModel):
    item_id: str
    title: str
    url: str
    image_url: str | None
    price: float | None
    price_type: str | None
    city: str | None


class PlatformPreviewResponse(BaseModel):
    marketplace: str
    label: str
    total_count: int | None
    post_filters: list[str]
    sample: list[ListingSampleResponse]
    error: str | None


class SearchPreviewResponse(BaseModel):
    description: list[str]
    platforms: list[PlatformPreviewResponse]


class SearchCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    filters: FiltersModel
    platforms: list[str] = Field(min_length=1, max_length=10)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    seller_type: SellerType = "all"
    alert_max_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    unknown_policy: UnknownPolicy = "include"


class SearchUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    exclude_keywords: list[str] | None = Field(default=None, max_length=50)
    seller_type: SellerType | None = None
    active: bool | None = None
    # null clears the ceiling (no alerts); omit the field to keep it.
    alert_max_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    filters: FiltersModel | None = None
    platforms: list[str] | None = Field(default=None, min_length=1, max_length=10)
    unknown_policy: UnknownPolicy | None = None


class CheapestListingResponse(BaseModel):
    item_id: str
    marketplace: str
    title: str
    url: str
    price: float
    archive_id: int | None


class SourceResponse(BaseModel):
    marketplace: str
    label: str
    post_filters: list[str]
    baseline_done: bool
    last_checked_at: datetime | None
    next_check_at: datetime | None
    last_status: str
    last_error_message: str | None
    last_total_count: int | None


class SearchResponse(BaseModel):
    id: int
    name: str
    filters: FiltersModel | None
    platforms: list[SourceResponse]
    description: list[str]
    exclude_keywords: list[str]
    seller_type: str
    alert_max_price: float | None
    unknown_policy: str
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


class AlsoListedResponse(BaseModel):
    """The same car on another platform."""

    id: int
    marketplace: str
    item_id: str
    url: str
    current_price: float | None
    city: str | None
    gone_at: datetime | None


class ListingResponse(BaseModel):
    id: int
    marketplace: str
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
    unverified_filters: list[str]
    is_new: bool
    first_seen_at: datetime
    last_seen_at: datetime
    gone_at: datetime | None
    price_history: list[ListingPricePointResponse]
    archive_id: int | None = None
    also_listed: list[AlsoListedResponse] = []


class ListingListResponse(BaseModel):
    search_id: int
    items: list[ListingResponse]
    # Name of the place distances are measured from (straight line), if set.
    distance_from: str | None = None


def _raise_for_marketplace(exc: MarketplaceError) -> None:
    status = 422 if exc.kind in {"invalid_url", "invalid_filter", "unsupported"} else 502
    raise HTTPException(status_code=status, detail=str(exc)) from exc


def _options_response(result: tuple[list[MergedOption], list[str]]) -> OptionListResponse:
    options, warnings = result
    return OptionListResponse(
        items=[OptionResponse(label=option.label, platforms=option.platforms) for option in options],
        warnings=warnings,
    )


def _cheapest_response(
    db_session: Session, search: MarketplaceSearch
) -> CheapestListingResponse | None:
    row = cheapest_listing(db_session, search)
    if row is None or row.current_price is None:
        return None
    archive_ids = archive_ids_for(db_session, owner_id=search.owner_id, item_ids=[row.item_id])
    return CheapestListingResponse(
        item_id=row.item_id,
        marketplace=row.marketplace,
        title=row.title,
        url=row.url,
        price=float(row.current_price),
        archive_id=archive_ids.get(row.item_id),
    )


def _to_response(db_session: Session, search: MarketplaceSearch) -> SearchResponse:
    listing_count, new_count = search_listing_counts(db_session, search)
    status = search_status(search)
    filters = get_search_filters(search)
    return SearchResponse(
        id=search.id,
        name=search.name,
        filters=FiltersModel(**filters.to_dict()) if filters is not None else None,
        platforms=[
            SourceResponse(
                marketplace=source.marketplace,
                label=platform_label(source.marketplace),
                post_filters=get_post_filters(source),
                baseline_done=source.baseline_done,
                last_checked_at=source.last_checked_at,
                next_check_at=source.next_check_at,
                last_status=source.last_status,
                last_error_message=source.last_error_message,
                last_total_count=source.last_total_count,
            )
            for source in search.sources
        ],
        description=get_search_description(search),
        exclude_keywords=get_exclude_keywords(search),
        seller_type=search.seller_type,
        alert_max_price=float(search.alert_max_price)
        if search.alert_max_price is not None
        else None,
        unknown_policy=search.unknown_policy,
        active=search.active,
        baseline_done=status.baseline_done,
        last_checked_at=status.last_checked_at,
        next_check_at=status.next_check_at,
        last_status=status.last_status,
        last_error_message=status.last_error_message,
        last_total_count=status.last_total_count,
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
        marketplace=row.marketplace,
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
        unverified_filters=json.loads(row.unverified_filters_json or "[]"),
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


@router.get("/platforms", response_model=PlatformListResponse)
def get_platforms(
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> PlatformListResponse:
    return PlatformListResponse(
        items=[PlatformResponse(key=key, label=adapter.label) for key, adapter in adapters.items()]
    )


@router.get("/makes", response_model=OptionListResponse)
def get_makes(
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> OptionListResponse:
    return _options_response(list_makes(adapters))


@router.get("/models", response_model=OptionListResponse)
def get_models(
    make: str = Query(min_length=1, max_length=100),
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> OptionListResponse:
    return _options_response(list_models(adapters, make))


@router.post("/preview", response_model=SearchPreviewResponse)
def preview(
    payload: SearchPreviewRequest,
    request: Request,
    identity: RequestIdentity = Depends(get_request_identity),
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> SearchPreviewResponse:
    enforce_write_rate_limit(request, identity)
    metrics.inc("api.searches.preview")
    try:
        result = preview_search(
            adapters,
            filters=payload.filters.to_filters(),
            platforms=payload.platforms,
            seller_type=payload.seller_type,
            exclude_keywords=payload.exclude_keywords,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SearchPreviewResponse(
        description=result.description,
        platforms=[
            PlatformPreviewResponse(
                marketplace=item.marketplace,
                label=platform_label(item.marketplace),
                total_count=item.total_count,
                post_filters=item.post_filters,
                sample=[_sample_response(listing) for listing in item.sample],
                error=item.error,
            )
            for item in result.platforms
        ],
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
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> SearchResponse:
    enforce_write_rate_limit(request, identity)
    metrics.inc("api.searches.create")
    try:
        search = create_search(
            db_session,
            adapters,
            owner_id=identity.owner_id,
            name=payload.name,
            filters=payload.filters.to_filters(),
            platforms=payload.platforms,
            exclude_keywords=payload.exclude_keywords,
            seller_type=payload.seller_type,
            alert_max_price=payload.alert_max_price,
            unknown_policy=payload.unknown_policy,
        )
    except MarketplaceError as exc:
        _raise_for_marketplace(exc)
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
    adapters: dict[str, PlatformAdapter] = Depends(get_platform_adapters),
) -> SearchResponse:
    enforce_write_rate_limit(request, identity)
    search = _get_owned_search(db_session, identity, search_id)
    try:
        search = update_search(
            db_session,
            adapters,
            search,
            name=payload.name,
            exclude_keywords=payload.exclude_keywords,
            seller_type=payload.seller_type,
            active=payload.active,
            filters=payload.filters.to_filters() if payload.filters is not None else None,
            platforms=payload.platforms,
            unknown_policy=payload.unknown_policy,
            **(
                {"alert_max_price": payload.alert_max_price}
                if "alert_max_price" in payload.model_fields_set
                else {}
            ),
        )
    except MarketplaceError as exc:
        db_session.rollback()
        _raise_for_marketplace(exc)
    except ValueError as exc:
        db_session.rollback()
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
    cars = list_search_cars(db_session, search)
    archive_ids = archive_ids_for(
        db_session, owner_id=identity.owner_id, item_ids=[row.item_id for car in cars for row in car]
    )
    home = home_location()
    return ListingListResponse(
        search_id=search.id,
        distance_from=home.name if home is not None else None,
        items=[_car_response(car, now, archive_ids) for car in cars],
    )


def _car_response(
    car: list[MarketplaceListing], now: datetime, archive_ids: dict[str, int]
) -> ListingResponse:
    """The main listing of a car, with the car's other platforms."""
    main, others = car[0], car[1:]
    first = earliest_listing(car)
    response = _listing_response(main, now, archive_ids.get(main.item_id))
    if archive_ids.get(main.item_id) is None:
        response.archive_id = next((archive_ids[row.item_id] for row in others if row.item_id in archive_ids), None)
    response.first_seen_at = first.first_seen_at
    response.is_new = is_listing_new(first, now)
    response.also_listed = [
        AlsoListedResponse(
            id=row.id,
            marketplace=row.marketplace,
            item_id=row.item_id,
            url=row.url,
            current_price=float(row.current_price) if row.current_price is not None else None,
            city=row.city,
            gone_at=row.gone_at,
        )
        for row in others
    ]
    return response
