"""
SQLAlchemy ORM models for the Real Estate Aggregation Platform.

Core tables:
- ``properties`` — LIST-partitioned by ``portal_source``
- ``agencies``   — Real estate agencies / property owners
- ``scraper_runs`` — Scraper execution history
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import geoalchemy2  # noqa: F401  # Required for PostGIS Geometry DDL
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


class Property(Base):
    """A real estate listing scraped from a portal.

    Partitioned by ``portal_source`` (LIST partitioning).
    """

    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("portal_source", "source_id", name="uq_properties_source"),
        {
            "postgresql_partition_by": "LIST (portal_source)",
            "info": {"partition_columns": ["portal_source"]},
        },
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    # NOTE: Spec F-2 originally called for UUID PK. Integer was chosen for
    # LIST-partitioning compatibility (partition key must be part of PK).
    # Decision record: doc/planning/epics/STORY-1/README.md
    portal_source: Mapped[str] = mapped_column(String(50), primary_key=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Content
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    auction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    offered_by: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Promotion
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promotion_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Pricing
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_currency: Mapped[str] = mapped_column(String(3), default="PLN", nullable=False)
    price_per_m2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Dimensions
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    plot_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    rooms: Mapped[str | None] = mapped_column(String(50), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    floors_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    heating: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extras: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Location
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location: Mapped[object | None] = mapped_column(
        geoalchemy2.Geometry("POINT", srid=4326),
        nullable=True,
    )

    # Agency
    agency_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agency_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Media
    photos: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    localization: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    building: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Deduplication
    duplicate_group_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return f"<{cls}(id={self.id}, portal={self.portal_source!r}, source_id={self.source_id!r})>"


# Indexes for Property (created manually in Alembic)
idx_properties_search = Index(
    "idx_properties_search",
    Property.city,
    Property.property_type,
    Property.auction_type,
    Property.price,
    postgresql_where=(Property.is_canonical.is_(True) & Property.is_active.is_(True)),
)
idx_properties_location = Index(
    "idx_properties_location",
    Property.location,
    postgresql_using="gist",
    postgresql_where=(Property.is_canonical.is_(True)),
)


# ---------------------------------------------------------------------------
# Agency
# ---------------------------------------------------------------------------


class Agency(Base):
    """A real estate agency or property owner."""

    __tablename__ = "agencies"
    __table_args__ = (UniqueConstraint("portal_source", "source_id", name="uq_agencies_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portal_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subscription_tier: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subscription_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    properties: Mapped[list["Property"]] = relationship(  # noqa: F811
        "Property",
        primaryjoin="and_(foreign(Property.agency_source_id) == Agency.source_id, "
        "foreign(Property.portal_source) == Agency.portal_source)",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Agency(id={self.id}, name={self.name!r})>"


# ---------------------------------------------------------------------------
# ScraperRun
# ---------------------------------------------------------------------------


class ScraperRunStatus(StrEnum):
    """Status values for a scraper run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScraperRun(Base):
    """Tracks a single execution of a portal scraper."""

    __tablename__ = "scraper_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    portal_source: Mapped[str] = mapped_column(String(50), nullable=False)
    scraper_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    listings_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=ScraperRunStatus.RUNNING.value,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ScraperRun(id={self.id}, portal={self.portal_source!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# PhotoAsset
# ---------------------------------------------------------------------------


class PhotoAsset(Base):
    """Metadata record for a user-uploaded photo stored in MinIO.

    Each row represents a single photo identified by its SHA-256 hash.
    Photos are stored in MinIO at ``photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg``
    with an optional 400×300 thumbnail alongside.
    """

    __tablename__ = "photo_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PhotoAsset(id={self.id}, sha256={self.sha256!r}, mime={self.mime_type!r})>"
