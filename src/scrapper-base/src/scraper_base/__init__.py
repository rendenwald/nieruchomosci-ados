"""
scrapper-base — shared infrastructure for portal-specific real estate scrapers.

Provides async PostgreSQL connectivity, BasePipeline ABC, Prometheus metrics,
structured logging, MinIO storage client, and Redis cache invalidation.
"""

from scraper_base.cache_invalidator import CacheInvalidator
from scraper_base.stream_publisher import StreamPublisher

__all__ = ["CacheInvalidator", "StreamPublisher"]

__version__ = "0.1.0"
