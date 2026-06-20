"""
Shared test fixtures for scrapper-base unit tests.

Uses in-memory SQLite for model/service tests by patching PostgreSQL-specific
types and geoalchemy2 DDL event handlers *before* any model imports.
"""

# ruff: noqa: E402, I001 — Module-level patching requires non-standard import ordering

# ---------------------------------------------------------------------------
# Patching: must happen before any model imports
# ---------------------------------------------------------------------------

import geoalchemy2 as _geoalchemy2  # noqa: F401 — triggers DDL listener registration
import geoalchemy2.admin.dialects.sqlite as _sqlite_dialect  # noqa: F401
import geoalchemy2.types as _ga_types  # noqa: F401

# Replace SpatiaLite-specific DDL handlers with no-ops for SQLite compatibility.
# The after_create handler calls RecoverGeometryColumn() which is a SpatiaLite
# function not available in plain SQLite.
_sqlite_dialect.before_create = lambda table, bind, **kw: None  # type: ignore[method-assign]
_sqlite_dialect.after_create = lambda table, bind, **kw: None  # type: ignore[method-assign]
_sqlite_dialect.before_drop = lambda table, bind, **kw: None  # type: ignore[method-assign]
_sqlite_dialect.after_drop = lambda table, bind, **kw: None  # type: ignore[method-assign]

# Patch geoalchemy2.types.Geometry to a simple type for SQLite
from sqlalchemy import String as _String
from sqlalchemy.types import TypeDecorator as _TypeDecorator


class _GeometryPatched(_TypeDecorator):
    """Replacement for geoalchemy2.Geometry that works with SQLite.

    Ignores Geometry-specific args (geometry_type, srid) since SQLite
    has no spatial type system.
    """

    impl = _String(255)
    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = -1) -> None:  # noqa: ARG002
        """Ignore geometry_type and srid; use our simple String impl."""
        super().__init__()

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(_String(255))


_ga_types.Geometry = _GeometryPatched  # type: ignore[misc]
_geoalchemy2.Geometry = _GeometryPatched  # type: ignore[assignment]  # Patch module-level ref too

# Patch PostgreSQL JSONB -> SQLite JSON
from sqlalchemy.dialects.sqlite import JSON as _SQLiteJson  # noqa: N811
import sqlalchemy.dialects.postgresql as _pg_types


class _JsonbPatched(_TypeDecorator):
    """Maps PostgreSQL JSONB to SQLite's JSON type."""

    impl = _SQLiteJson
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(_SQLiteJson())
        return super().load_dialect_impl(dialect)


_pg_types.JSONB = _JsonbPatched

# Patch PostgreSQL UUID -> String for ScraperRun.id
from sqlalchemy.types import String as _StringType


class _UuidPatched(_TypeDecorator):
    """Maps PostgreSQL UUID to SQLite String(36)."""

    impl = _StringType(36)
    cache_ok = True

    def __init__(self, as_uuid: bool = True) -> None:  # noqa: ARG002
        """Ignore the as_uuid parameter; always use a string."""
        super().__init__()

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(_StringType(36))


_pg_types.UUID = _UuidPatched

# ---------------------------------------------------------------------------
# Standard imports (after all patches)
# ---------------------------------------------------------------------------

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from scraper_base.models import Base

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine():
    """Create an async SQLite in-memory engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh async session for each test."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PROPERTY = {
    "portal_source": "otodom",
    "source_id": "OTODOM-12345",
    "source_url": "https://www.otodom.pl/...",
    "title": "Mieszkanie 2 pokoje, 50m\u00b2",
    "description": "Pi\u0119kne mieszkanie w centrum miasta.",
    "property_type": "apartment",
    "market_type": "secondary",
    "offered_by": "owner",
    "price": 520000,
    "price_currency": "PLN",
    "price_per_m2": 10400,
    "area": 50.0,
    "rooms": "2",
    "floor": "3",
    "floors_total": 5,
    "city": "Warszawa",
    "district": "\u015ar\u00f3dmie\u015bcie",
    "province": "mazowieckie",
    "latitude": 52.2297,
    "longitude": 21.0122,
    "is_active": True,
}

SAMPLE_AGENCY = {
    "portal_source": "otodom",
    "source_id": "AGENCY-001",
    "name": "Nieruchomo\u015bci ABC",
    "city": "Warszawa",
    "province": "mazowieckie",
}


@pytest.fixture
def sample_property() -> dict[str, Any]:
    """Return a sample property dict for testing."""
    return dict(SAMPLE_PROPERTY)


@pytest.fixture
def sample_agency() -> dict[str, Any]:
    """Return a sample agency dict for testing."""
    return dict(SAMPLE_AGENCY)


# ---------------------------------------------------------------------------
# MinIO mock
# ---------------------------------------------------------------------------


class MockMinioClient:
    """In-memory mock of MinioStorageClient for testing."""

    def __init__(self) -> None:
        self._buckets: set[str] = set()
        self._objects: dict[str, bytes] = {}
        self.is_available = True
        self._initialised = True

    async def ensure_bucket(self, bucket: str | None = None) -> bool:
        target = bucket or "test-bucket"
        self._buckets.add(target)
        return True

    async def upload_photo(
        self,
        data: bytes,
        object_name: str | None = None,
        content_type: str = "image/jpeg",
    ) -> str | None:
        obj_name = object_name or f"test/{uuid.uuid4()}.jpg"
        self._objects[obj_name] = data
        return obj_name

    async def get_photo_url(
        self,
        object_name: str,
        expires_seconds: int = 3600,
    ) -> str | None:
        return (
            f"http://minio-test.local/{object_name}?expires={expires_seconds}"
        )


@pytest.fixture
def mock_minio() -> MockMinioClient:
    """Return a mock MinIO client."""
    return MockMinioClient()
