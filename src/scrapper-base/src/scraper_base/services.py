"""
Business logic services for property and agency persistence.

Provides ``PropertyService`` and ``AgencyService`` with upsert semantics.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from scraper_base.models import Agency, Property, ScraperRun, ScraperRunStatus

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic validation schemas
# ---------------------------------------------------------------------------


class PropertyCreate(BaseModel):
    """Validation schema for new property data.

    All fields are optional except those with no default.
    """

    id: int | None = Field(None, ge=0, description="Auto-generated via identity column; provide for SQLite")
    portal_source: str = Field(..., min_length=1, max_length=50)
    source_id: str = Field(..., min_length=1, max_length=255)
    source_url: str | None = None
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    property_type: str | None = Field(None, max_length=50)
    auction_type: str | None = Field(None, max_length=20)
    market_type: str | None = Field(None, max_length=20)
    offered_by: str | None = Field(None, max_length=20)
    is_promoted: bool = False
    promotion_expires_at: datetime | None = None
    price: int | None = Field(None, ge=0)
    price_currency: str = "PLN"
    price_per_m2: int | None = Field(None, ge=0)
    rent: int | None = Field(None, ge=0)
    area: float | None = Field(None, ge=0)
    plot_area: float | None = Field(None, ge=0)
    rooms: str | None = Field(None, max_length=50)
    floor: str | None = Field(None, max_length=50)
    floors_total: int | None = Field(None, ge=0)
    year_built: int | None = Field(None, ge=1800, le=2030)
    condition: str | None = Field(None, max_length=50)
    heating: str | None = Field(None, max_length=100)
    extras: dict[str, Any] | None = None
    province: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    district: str | None = Field(None, max_length=100)
    street: str | None = Field(None, max_length=255)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    agency_name: str | None = Field(None, max_length=255)
    agency_source_id: str | None = Field(None, max_length=255)
    photos: list[dict[str, Any]] | None = None
    localization: dict[str, Any] | None = None
    building: dict[str, Any] | None = None
    source_created_at: datetime | None = None
    is_active: bool = True

    @field_validator("photos", mode="before")
    @classmethod
    def validate_photos(cls, v: Any) -> Any:
        """Accept either a list or a dict for the photos field."""
        if v is None:
            return v
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return [v]
        return v

    model_config = ConfigDict(extra="forbid")


class PropertyUpdate(BaseModel):
    """Validation schema for partial property updates."""

    source_url: str | None = None
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    property_type: str | None = Field(None, max_length=50)
    auction_type: str | None = Field(None, max_length=20)
    market_type: str | None = Field(None, max_length=20)
    offered_by: str | None = Field(None, max_length=20)
    is_promoted: bool | None = None
    promotion_expires_at: datetime | None = None
    price: int | None = Field(None, ge=0)
    price_currency: str | None = None
    price_per_m2: int | None = Field(None, ge=0)
    rent: int | None = Field(None, ge=0)
    area: float | None = Field(None, ge=0)
    plot_area: float | None = Field(None, ge=0)
    rooms: str | None = Field(None, max_length=50)
    floor: str | None = Field(None, max_length=50)
    floors_total: int | None = Field(None, ge=0)
    year_built: int | None = Field(None, ge=1800, le=2030)
    condition: str | None = Field(None, max_length=50)
    heating: str | None = Field(None, max_length=100)
    extras: dict[str, Any] | None = None
    province: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    district: str | None = Field(None, max_length=100)
    street: str | None = Field(None, max_length=255)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    agency_name: str | None = Field(None, max_length=255)
    agency_source_id: str | None = Field(None, max_length=255)
    photos: list[dict[str, Any]] | None = None
    localization: dict[str, Any] | None = None
    building: dict[str, Any] | None = None
    is_active: bool | None = None
    source_created_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class AgencyCreate(BaseModel):
    """Validation schema for new agency data."""

    portal_source: str = Field(..., min_length=1, max_length=50)
    source_id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    nip: str | None = Field(None, max_length=20)
    street: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    province: str | None = Field(None, max_length=100)
    postal_code: str | None = Field(None, max_length=20)
    subscription_tier: str | None = Field(None, max_length=50)
    subscription_expires: datetime | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# PropertyService
# ---------------------------------------------------------------------------


class PropertyService:
    """Service for managing real estate property records.

    Provides upsert, query, and soft-delete operations.

    Uses an atomic ``INSERT ... ON CONFLICT DO UPDATE`` upsert on PostgreSQL
    for concurrent safety, with a SELECT-then-INSERT/UPDATE fallback for SQLite.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # Detect dialect once — immutable for the lifetime of the service.
        # PostgreSQL gets the atomic upsert path; SQLite uses the fallback.
        self._dialect: str = "sqlite"
        if session.bind is not None:
            self._dialect = session.bind.dialect.name

    async def upsert_property(
        self,
        data: dict[str, Any],
    ) -> tuple[Property, bool]:
        """Insert or update a property record.

        Matches on ``(portal_source, source_id)``. Uses an atomic upsert
        (PostgreSQL ``ON CONFLICT DO UPDATE``) to prevent race conditions
        under concurrent access.

        Args:
            data: Raw property data dict. Validated against ``PropertyCreate``.

        Returns:
            A tuple of ``(property, is_new)`` where ``is_new`` is ``True`` for
            newly inserted records.

        Raises:
            ValueError: If validation fails.

        """
        # ── Validate ──────────────────────────────────────────────────────
        validated = PropertyCreate.model_validate(data)
        now = datetime.now(UTC)
        excluded = {"portal_source", "source_id", "id"}

        # ── PostgreSQL: atomic upsert via ON CONFLICT DO UPDATE ───────────
        if self._dialect == "postgresql":
            from typing import cast  # noqa: PLC0415

            from sqlalchemy import Table  # noqa: PLC0415
            from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415

            table = cast("Table", Property.__table__)

            property_data = validated.model_dump(exclude_none=True)
            property_data["scraped_at"] = now
            property_data["last_seen_at"] = now

            # Fields to set when a conflict (existing row) is found
            update_data = {
                k: v
                for k, v in property_data.items()
                if k not in excluded and k != "scraped_at"
            }
            update_data["last_seen_at"] = now

            insert_stmt = pg_insert(table).values(**property_data)
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["portal_source", "source_id"],
                set_=update_data,
            )
            await self.session.execute(upsert_stmt)

            # Re-fetch the ORM object after the upsert
            stmt = select(Property).where(
                Property.portal_source == validated.portal_source,
                Property.source_id == validated.source_id,
            )
            result = await self.session.execute(stmt)
            property_obj = result.scalar_one()

            # Option A: is_new detection via timestamp comparison.
            # On INSERT both scraped_at and last_seen_at are set to the same
            # ``now`` value. On UPDATE only last_seen_at is refreshed.
            is_new = property_obj.scraped_at == property_obj.last_seen_at
            return property_obj, is_new

        # ── SQLite fallback: SELECT-then-INSERT/UPDATE ───────────────────
        stmt = select(Property).where(
            Property.portal_source == validated.portal_source,
            Property.source_id == validated.source_id,
        )
        result = await self.session.execute(stmt)
        existing: Property | None = result.scalar_one_or_none()

        if existing is not None:
            # Update existing record
            update_data = validated.model_dump(exclude_none=True, exclude=excluded)
            update_data["last_seen_at"] = now
            for key, value in update_data.items():
                setattr(existing, key, value)
            self.session.add(existing)
            await self.session.flush()
            return existing, False

        # Insert new record with max(id)+1 fallback for SQLite
        property_data = validated.model_dump(exclude_none=True)
        property_data["scraped_at"] = now
        property_data["last_seen_at"] = now

        if "id" not in property_data:
            max_id_stmt = select(
                sa_func.coalesce(sa_func.max(Property.id), 0) + 1,
            ).where(Property.portal_source == validated.portal_source)
            next_id = await self.session.scalar(max_id_stmt)
            property_data["id"] = next_id

        new_property = Property(**property_data)
        self.session.add(new_property)
        await self.session.flush()
        await self.session.refresh(new_property)
        return new_property, True

    async def get_by_source(
        self,
        portal: str,
        source_id: str,
    ) -> Property | None:
        """Find a property by its portal and source ID.

        Args:
            portal: Portal source identifier (e.g. ``"otodom"``).
            source_id: Source-specific identifier.

        Returns:
            The ``Property`` if found, ``None`` otherwise.

        """
        stmt = select(Property).where(
            Property.portal_source == portal,
            Property.source_id == source_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_listings(
        self,
        portal: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Property]:
        """Return active listings, optionally filtered by portal.

        Args:
            portal: If set, only return listings from this portal.
            limit: Maximum number of results (default 100).
            offset: Pagination offset (default 0).

        Returns:
            A list of ``Property`` records.

        """
        stmt = select(Property).where(Property.is_active.is_(True))
        if portal:
            stmt = stmt.where(Property.portal_source == portal)
        stmt = stmt.order_by(Property.last_seen_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_inactive(
        self,
        portal: str,
        older_than: datetime | None = None,
    ) -> int:
        """Soft-delete properties not seen since a given time.

        Args:
            portal: Portal source to target.
            older_than: Cutoff timestamp. Defaults to 24 hours ago.

        Returns:
            Number of properties marked inactive.

        """
        if older_than is None:
            older_than = datetime.now(UTC) - timedelta(hours=24)
        stmt = (
            sa_update(Property)
            .where(
                Property.portal_source == portal,
                Property.last_seen_at < older_than,
                Property.is_active.is_(True),
            )
            .values(is_active=False)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount  # type: ignore  # CursorResult has rowcount at runtime

    async def count_active(self, portal: str | None = None) -> int:
        """Count active properties, optionally by portal.

        Args:
            portal: If set, count only for this portal.

        Returns:
            Total number of active properties.

        """
        stmt = select(sa_func.count(Property.id)).where(Property.is_active.is_(True))
        if portal:
            stmt = stmt.where(Property.portal_source == portal)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0


# ---------------------------------------------------------------------------
# AgencyService
# ---------------------------------------------------------------------------


class AgencyService:
    """Service for managing agency records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_agency(self, data: dict[str, Any]) -> Agency:
        """Insert or update an agency record.

        Matches on ``(portal_source, source_id)``.

        Args:
            data: Agency data dict. Validated against ``AgencyCreate``.

        Returns:
            The ``Agency`` record (existing or newly created).

        Raises:
            ValueError: If validation fails.

        """
        validated = AgencyCreate.model_validate(data)
        stmt = select(Agency).where(
            Agency.portal_source == validated.portal_source,
            Agency.source_id == validated.source_id,
        )
        result = await self.session.execute(stmt)
        existing: Agency | None = result.scalar_one_or_none()

        if existing is not None:
            excluded = {"portal_source", "source_id"}
            update_data = validated.model_dump(exclude_none=True, exclude=excluded)
            for key, value in update_data.items():
                setattr(existing, key, value)
            self.session.add(existing)
            await self.session.flush()
            return existing

        new_agency = Agency(**validated.model_dump(exclude_none=True))
        self.session.add(new_agency)
        await self.session.flush()
        await self.session.refresh(new_agency)
        return new_agency

    async def get_by_source(
        self,
        portal: str,
        source_id: str,
    ) -> Agency | None:
        """Find an agency by its portal and source ID."""
        stmt = select(Agency).where(
            Agency.portal_source == portal,
            Agency.source_id == source_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# ScraperRunService
# ---------------------------------------------------------------------------


class ScraperRunService:
    """Service for tracking scraper execution runs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(
        self,
        portal_source: str,
        scraper_id: str | None = None,
    ) -> ScraperRun:
        """Create a new scraper run record.

        Args:
            portal_source: Portal being scraped.
            scraper_id: Optional identifier for the scraper instance.

        Returns:
            The newly created ``ScraperRun``.

        """
        run = ScraperRun(
            portal_source=portal_source,
            scraper_id=scraper_id,
            status=ScraperRunStatus.RUNNING,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def complete_run(
        self,
        run_id: str,
        listings_scraped: int = 0,
        listings_new: int = 0,
        listings_updated: int = 0,
        errors_count: int = 0,
        error_message: str | None = None,
    ) -> ScraperRun | None:
        """Mark a scraper run as completed or failed.

        Args:
            run_id: The scraper run UUID.
            listings_scraped: Total items processed.
            listings_new: New items inserted.
            listings_updated: Existing items updated.
            errors_count: Number of errors encountered.
            error_message: Error description if failed.

        Returns:
            The updated ``ScraperRun``, or ``None`` if not found.

        """
        now = datetime.now(UTC)
        stmt = select(ScraperRun).where(ScraperRun.id == run_id)
        result = await self.session.execute(stmt)
        run: ScraperRun | None = result.scalar_one_or_none()

        if run is None:
            logger.warning("ScraperRun not found", run_id=run_id)
            return None

        run.finished_at = now
        run.listings_scraped = listings_scraped
        run.listings_new = listings_new
        run.listings_updated = listings_updated
        run.errors_count = errors_count
        run.error_message = error_message
        # Handle offset-aware vs offset-naive (e.g. SQLite) comparison
        if run.started_at.tzinfo is not None:
            run.duration_seconds = (now - run.started_at).total_seconds()
        else:
            run.duration_seconds = (now.replace(tzinfo=None) - run.started_at).total_seconds()

        if error_message:
            run.status = ScraperRunStatus.FAILED
        else:
            run.status = ScraperRunStatus.COMPLETED

        self.session.add(run)
        await self.session.flush()
        return run
