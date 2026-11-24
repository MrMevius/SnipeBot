from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WatchItem(Base):
    __tablename__ = "watch_items"
    __table_args__ = (
        UniqueConstraint("owner_id", "normalized_url", name="uq_watch_owner_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="local", index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    custom_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    site_key: Mapped[str] = mapped_column(String(64), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    first_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(nullable=False, default=0)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dead_letter_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    check_count: Mapped[int] = mapped_column(nullable=False, default=0)
    successful_check_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    checks: Mapped[list["PriceCheck"]] = relationship(
        back_populates="watch_item", cascade="all, delete-orphan"
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="watch_item", cascade="all, delete-orphan"
    )
    tags: Mapped[list["WatchItemTag"]] = relationship(
        secondary="watch_item_tag_links",
        back_populates="items",
    )


class PriceCheck(Base):
    __tablename__ = "price_checks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watch_item_id: Mapped[int] = mapped_column(
        ForeignKey("watch_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    adapter_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parser_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    used_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    watch_item: Mapped[WatchItem] = relationship(back_populates="checks")
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="price_check"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    watch_item_id: Mapped[int] = mapped_column(
        ForeignKey("watch_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_check_id: Mapped[int] = mapped_column(
        ForeignKey("price_checks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    price_check_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    alert_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    label_or_title: Mapped[str] = mapped_column(String(512), nullable=False)
    site_key: Mapped[str] = mapped_column(String(64), nullable=False)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    watch_item: Mapped[WatchItem] = relationship(back_populates="alert_events")
    price_check: Mapped[PriceCheck] = relationship(back_populates="alert_events")


class WatchItemTag(Base):
    __tablename__ = "watch_item_tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_watch_tag_owner_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    items: Mapped[list[WatchItem]] = relationship(
        secondary="watch_item_tag_links",
        back_populates="tags",
    )


class WatchItemTagLink(Base):
    __tablename__ = "watch_item_tag_links"
    __table_args__ = (
        UniqueConstraint("watch_item_id", "tag_id", name="uq_watch_item_tag_link"),
    )

    watch_item_id: Mapped[int] = mapped_column(
        ForeignKey("watch_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("watch_item_tags.id", ondelete="CASCADE"), primary_key=True
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MarketplaceSearch(Base):
    __tablename__ = "marketplace_searches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="local", index=True
    )
    marketplace: Mapped[str] = mapped_column(
        String(32), nullable=False, default="marktplaats"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    query_json: Mapped[str] = mapped_column(Text, nullable=False)
    description_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    exclude_keywords_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    seller_type: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    baseline_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Highest numeric listing id known for this search. Unseen listings below
    # it are older ads that were bumped back to the top, not new ones.
    id_watermark: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_total_count: Mapped[int | None] = mapped_column(nullable=True)
    last_fetched_count: Mapped[int | None] = mapped_column(nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    last_error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(nullable=False, default=0)
    check_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    listings: Mapped[list["MarketplaceListing"]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )
    alert_events: Mapped[list["MarketplaceAlertEvent"]] = relationship(
        back_populates="search", cascade="all, delete-orphan"
    )


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        UniqueConstraint("search_id", "item_id", name="uq_marketplace_listing_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("marketplace_searches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    distance_meters: Mapped[int | None] = mapped_column(nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    from_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    gone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    search: Mapped[MarketplaceSearch] = relationship(back_populates="listings")
    prices: Mapped[list["MarketplaceListingPrice"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="MarketplaceListingPrice.observed_at",
    )


class MarketplaceListingPrice(Base):
    __tablename__ = "marketplace_listing_prices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    listing: Mapped[MarketplaceListing] = relationship(back_populates="prices")


class MarketplaceAlertEvent(Base):
    __tablename__ = "marketplace_alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("marketplace_searches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alert_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    search: Mapped[MarketplaceSearch] = relationship(back_populates="alert_events")
