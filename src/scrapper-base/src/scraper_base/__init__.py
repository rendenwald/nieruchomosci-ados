"""
scrapper-base — shared infrastructure for portal-specific real estate scrapers.

Provides async PostgreSQL connectivity, BasePipeline ABC, Prometheus metrics,
structured logging, MinIO storage client, and Redis cache invalidation.
"""

from scraper_base.cache_invalidator import CacheInvalidator

__all__ = ["CacheInvalidator"]

__version__ = "0.1.0"
