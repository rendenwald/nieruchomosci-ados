"""
Database utility helpers.

Provides convenience functions for initialisation and health-checking.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def check_connection(engine: AsyncEngine) -> bool:
    """Return ``True`` if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def property_count(session: AsyncSession, portal: str | None = None) -> int:
    """Return the total number of properties, optionally filtered by portal."""
    from scraper_base.models import Property  # noqa: PLC0415

    stmt = __import__("sqlalchemy").select(__import__("sqlalchemy").func.count(Property.id))
    if portal:
        stmt = stmt.where(Property.portal_source == portal)
    result = await session.execute(stmt)
    return result.scalar_one()
