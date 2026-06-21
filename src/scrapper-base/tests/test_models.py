"""Tests for the ORM model definitions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper_base.models import Agency, Property, ScraperRun, ScraperRunStatus


class TestPropertyModel:
    """Property model schema and constraints."""

    async def test_create_property(self, db_session: AsyncSession):
        """A valid property can be created and persisted."""
        prop = Property(
            id=1,
            portal_source="otodom",
            source_id="OTODOM-001",
            title="Test property",
            price=350000,
            city="Kraków",
            area=45.0,
        )
        db_session.add(prop)
        await db_session.commit()

        result = await db_session.execute(
            select(Property).where(Property.source_id == "OTODOM-001"),
        )
        loaded = result.scalar_one()
        assert loaded.portal_source == "otodom"
        assert loaded.title == "Test property"
        assert loaded.price == 350000
        assert loaded.is_active is True
        assert loaded.is_canonical is True
        assert loaded.price_currency == "PLN"

    async def test_pk_is_composite(self, db_session: AsyncSession):
        """Primary key spans (id, portal_source)."""
        pk_cols = [c.name for c in Property.__table__.primary_key]
        assert "id" in pk_cols
        assert "portal_source" in pk_cols

    async def test_partitioned_table(self):
        """Table metadata includes partition configuration."""
        args = Property.__table__.kwargs
        assert args.get("postgresql_partition_by") == "LIST (portal_source)"

    async def test_timestamps_default_to_now(self, db_session: AsyncSession):
        """Timestamps are auto-populated on creation."""
        prop = Property(
            id=2,
            portal_source="gratka",
            source_id="GRATKA-001",
            title="Auto timestamp test",
        )
        db_session.add(prop)
        await db_session.commit()

        assert prop.scraped_at is not None
        assert prop.last_seen_at is not None

    async def test_photos_jsonb(self, db_session: AsyncSession):
        """Photos field stores JSON data."""
        photos = [{"url": "https://example.com/photo1.jpg", "order": 1}]
        prop = Property(
            id=3,
            portal_source="otodom",
            source_id="OTODOM-PHOTO",
            photos=photos,
        )
        db_session.add(prop)
        await db_session.commit()

        assert prop.photos == photos


class TestAgencyModel:
    """Agency model."""

    async def test_create_agency(self, db_session: AsyncSession):
        """A valid agency can be created and persisted."""
        agency = Agency(
            portal_source="otodom",
            source_id="AGENCY-001",
            name="Test Agency",
            city="Warszawa",
        )
        db_session.add(agency)
        await db_session.commit()

        result = await db_session.execute(
            select(Agency).where(Agency.source_id == "AGENCY-001"),
        )
        loaded = result.scalar_one()
        assert loaded.name == "Test Agency"
        assert loaded.city == "Warszawa"
        assert loaded.created_at is not None


class TestScraperRunModel:
    """ScraperRun model."""

    async def test_create_run(self, db_session: AsyncSession):
        """A scraper run starts in running status."""
        run = ScraperRun(
            portal_source="otodom",
            scraper_id="scraper-1",
        )
        db_session.add(run)
        await db_session.commit()

        assert run.status == ScraperRunStatus.RUNNING
        assert run.started_at is not None
        assert run.listings_scraped == 0
        assert run.errors_count == 0

    async def test_complete_run(self, db_session: AsyncSession):
        """Run can be marked as completed."""
        run = ScraperRun(
            portal_source="otodom",
            scraper_id="scraper-1",
        )
        db_session.add(run)
        await db_session.commit()

        run.status = ScraperRunStatus.COMPLETED
        run.listings_scraped = 10
        run.errors_count = 0
        await db_session.commit()

        assert run.status == ScraperRunStatus.COMPLETED
