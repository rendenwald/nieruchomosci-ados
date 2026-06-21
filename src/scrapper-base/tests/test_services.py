"""Tests for service layer (PropertyService, AgencyService, ScraperRunService)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper_base.models import Property
from scraper_base.services import AgencyService, PropertyService, ScraperRunService


class TestPropertyService:
    """PropertyService business logic."""

    async def test_upsert_new(self, db_session: AsyncSession, sample_property):
        """New property is inserted and is_new=True."""
        service = PropertyService(db_session)
        prop, is_new = await service.upsert_property(sample_property)
        assert is_new is True
        assert prop.portal_source == "otodom"
        assert prop.source_id == "OTODOM-12345"
        assert prop.title == "Mieszkanie 2 pokoje, 50m²"
        assert prop.price == 520000

    async def test_upsert_existing(self, db_session: AsyncSession, sample_property):
        """Existing property is updated and is_new=False."""
        from datetime import UTC, datetime  # noqa: PLC0415

        service = PropertyService(db_session)

        # Insert first
        await service.upsert_property(sample_property)

        # Capture the timestamp just before the upsert
        before = datetime.now(UTC)

        # Upsert again with updated data
        updated_data = dict(sample_property)
        updated_data["price"] = 500000
        updated_data["title"] = "Updated title"

        prop2, is_new2 = await service.upsert_property(updated_data)
        assert is_new2 is False
        assert prop2.price == 500000
        assert prop2.title == "Updated title"
        # last_seen_at should be refreshed to a time after ``before``
        assert prop2.last_seen_at is not None
        assert prop2.last_seen_at >= before

    async def test_upsert_same_key_no_duplicate(self, db_session: AsyncSession, sample_property):
        """Upserting the same key twice does not create a duplicate."""
        service = PropertyService(db_session)
        await service.upsert_property(sample_property)
        await service.upsert_property(sample_property)

        result = await db_session.execute(
            select(Property).where(
                Property.portal_source == "otodom",
                Property.source_id == "OTODOM-12345",
            ),
        )
        rows = result.scalars().all()
        assert len(rows) == 1

    async def test_upsert_invalid_data(self, db_session: AsyncSession):
        """Invalid data raises ValueError."""
        service = PropertyService(db_session)
        with pytest.raises(ValueError, match="Field required"):
            await service.upsert_property({"portal_source": "otodom"})

    async def test_get_by_source_found(self, db_session: AsyncSession, sample_property):
        """get_by_source returns the matching property."""
        service = PropertyService(db_session)
        await service.upsert_property(sample_property)

        prop = await service.get_by_source("otodom", "OTODOM-12345")
        assert prop is not None
        assert prop.source_id == "OTODOM-12345"

    async def test_get_by_source_not_found(self, db_session: AsyncSession):
        """get_by_source returns None for non-existent property."""
        service = PropertyService(db_session)
        prop = await service.get_by_source("otodom", "NONEXISTENT")
        assert prop is None

    async def test_get_active_listings(self, db_session: AsyncSession, sample_property):
        """Active listings are returned correctly."""
        service = PropertyService(db_session)
        await service.upsert_property(sample_property)

        listings = await service.get_active_listings(portal="otodom")
        assert len(listings) == 1
        assert listings[0].source_id == "OTODOM-12345"

    async def test_get_active_listings_empty(self, db_session: AsyncSession):
        """No listings returns empty list."""
        service = PropertyService(db_session)
        listings = await service.get_active_listings(portal="otodom")
        assert listings == []

    async def test_count_active(self, db_session: AsyncSession, sample_property):
        """count_active returns correct count."""
        service = PropertyService(db_session)
        await service.upsert_property(sample_property)
        # Insert another property
        prop2 = dict(sample_property)
        prop2["id"] = 2
        prop2["source_id"] = "OTODOM-67890"
        await service.upsert_property(prop2)

        count = await service.count_active("otodom")
        assert count == 2

    async def test_mark_inactive(self, db_session: AsyncSession, sample_property):
        """mark_inactive soft-deletes old properties."""
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        service = PropertyService(db_session)
        await service.upsert_property(sample_property)

        # Mark with an old cutoff
        cutoff = datetime.now(UTC) + timedelta(hours=1)
        count = await service.mark_inactive("otodom", older_than=cutoff)
        assert count == 1

        # Verify property is now inactive
        prop = await service.get_by_source("otodom", "OTODOM-12345")
        assert prop is not None
        assert prop.is_active is False

    async def test_concurrent_upsert_same_key(self, db_engine, sample_property):
        """Concurrent upserts of the same key do not produce duplicates.

        Note: This test requires proper transaction isolation (PostgreSQL).
        On SQLite with StaticPool, concurrent sessions share the underlying
        connection which can cause false positives. The sequential variant
        (test_upsert_same_key_no_duplicate) is the primary guard.
        """
        import asyncio  # noqa: PLC0415

        from sqlalchemy.ext.asyncio import AsyncSession  # noqa: PLC0415

        async def _upsert_in_session():
            async with AsyncSession(bind=db_engine) as session:
                service = PropertyService(session)
                try:
                    return await service.upsert_property(sample_property)
                except Exception as exc:
                    return exc

        results = await asyncio.gather(
            _upsert_in_session(),
            _upsert_in_session(),
            return_exceptions=True,
        )

        successes = [r for r in results if isinstance(r, tuple) and len(r) == 2]

        # At least one insert must succeed regardless of isolation
        # (the other may get a constraint violation on SQLite)
        if len(successes) == 0:
            msg = "Both concurrent upserts failed — this can happen on SQLite with StaticPool"
            raise pytest.skip(msg)  # noqa: TRY301

        # Exactly one row in the database
        async with AsyncSession(bind=db_engine) as session:
            result = await session.execute(
                select(Property).where(
                    Property.portal_source == "otodom",
                    Property.source_id == "OTODOM-12345",
                ),
            )
            rows = result.scalars().all()
            assert len(rows) == 1


class TestAgencyService:
    """AgencyService business logic."""

    async def test_upsert_new(self, db_session: AsyncSession, sample_agency):
        """New agency is inserted."""
        service = AgencyService(db_session)
        agency = await service.upsert_agency(sample_agency)
        assert agency.name == "Nieruchomości ABC"
        assert agency.portal_source == "otodom"

    async def test_upsert_existing(self, db_session: AsyncSession, sample_agency):
        """Existing agency is updated."""
        service = AgencyService(db_session)
        await service.upsert_agency(sample_agency)

        updated = dict(sample_agency)
        updated["name"] = "Nieruchomości XYZ"
        agency = await service.upsert_agency(updated)
        assert agency.name == "Nieruchomości XYZ"

    async def test_get_by_source(self, db_session: AsyncSession, sample_agency):
        """get_by_source returns the matching agency."""
        service = AgencyService(db_session)
        await service.upsert_agency(sample_agency)

        agency = await service.get_by_source("otodom", "AGENCY-001")
        assert agency is not None
        assert agency.name == "Nieruchomości ABC"


class TestScraperRunService:
    """ScraperRunService business logic."""

    async def test_create_run(self, db_session: AsyncSession):
        """A new run is created with running status."""
        service = ScraperRunService(db_session)
        run = await service.create_run("otodom", scraper_id="test-scraper")
        assert run.portal_source == "otodom"
        assert run.scraper_id == "test-scraper"
        assert run.status == "running"
        assert run.listings_scraped == 0

    async def test_complete_run(self, db_session: AsyncSession):
        """A run can be completed with stats."""
        service = ScraperRunService(db_session)
        run = await service.create_run("otodom")
        updated = await service.complete_run(
            run_id=run.id,
            listings_scraped=10,
            listings_new=5,
            listings_updated=3,
            errors_count=2,
        )
        assert updated is not None
        assert updated.status == "completed"
        assert updated.listings_scraped == 10
        assert updated.listings_new == 5
        assert updated.duration_seconds is not None

    async def test_complete_run_with_error(self, db_session: AsyncSession):
        """A run with errors is marked as failed."""
        service = ScraperRunService(db_session)
        run = await service.create_run("gratka")
        updated = await service.complete_run(
            run_id=run.id,
            error_message="Connection timeout",
        )
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "Connection timeout"
