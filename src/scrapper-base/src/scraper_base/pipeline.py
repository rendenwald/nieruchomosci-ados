"""
BasePipeline — abstract base class for Scrapy pipelines.

All portal-specific scrapers subclass ``BasePipeline`` and implement the
``item_to_data()`` method. The base class handles database connectivity,
metrics auto-emission, structured logging, and MinIO storage.
"""

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from scraper_base.database import create_async_engine, create_session_factory
from scraper_base.logging_config import get_logger
from scraper_base.metrics import (
    increment_errors,
    increment_listings_scraped,
    observe_db_write,
    set_active_listings,
)
from scraper_base.services import PropertyService, ScraperRunService
from scraper_base.storage import MinioStorageClient


class BasePipeline(ABC):
    """Abstract base class for Scrapy pipelines.

    Subclasses must set ``PORTAL_SOURCE`` and implement ``item_to_data()``.

    Usage::

        class OtodomPipeline(BasePipeline):
            PORTAL_SOURCE = "otodom"

            def item_to_data(self, item: ScrapyItem) -> dict:
                return { ... }

    """

    PORTAL_SOURCE: str = "unknown"

    def __init__(self) -> None:
        _check_portal_source(self.PORTAL_SOURCE)

        self._db_engine: Any = None
        self._session_factory: Any = None
        self._session: Any = None
        self._minio: MinioStorageClient | None = None
        self._property_service: PropertyService | None = None
        self._run_service: ScraperRunService | None = None
        self._run_id: str | None = None
        self._items_scraped: int = 0
        self._items_new: int = 0
        self._items_updated: int = 0
        self._errors: int = 0
        self._start_time: float = 0.0

        # Logger with consistent fields
        self._scraper_id = str(uuid.uuid4())
        self.logger = get_logger(
            portal=self.PORTAL_SOURCE,
            scraper_id=self._scraper_id,
            run_id="pending",
        )

    # ------------------------------------------------------------------
    # Hooks — subclasses override item_to_data()
    # ------------------------------------------------------------------

    @abstractmethod
    def item_to_data(self, item: Any) -> dict[str, Any]:
        """Convert a scraped ``ScrapyItem`` into a property data dict.

        The returned dict must contain at minimum ``portal_source`` and
        ``source_id``. See ``PropertyCreate`` for the full schema.

        Args:
            item: The raw Scrapy item from the spider.

        Returns:
            A dictionary matching the ``PropertyCreate`` schema.

        """
        ...

    # ------------------------------------------------------------------
    # Spider lifecycle
    # ------------------------------------------------------------------

    async def open_spider(self, spider: Any) -> None:  # noqa: ANN401
        """Initialise connections when the spider opens.

        Creates database engine, session, MinIO client, and records the
        scraper run start.

        Args:
            spider: The Scrapy ``Spider`` instance (unused, enables override).

        """
        from scraper_base.database import get_database_url  # noqa: PLC0415

        self._start_time = time.monotonic()

        # Database
        db_url = get_database_url()
        self._db_engine = create_async_engine(db_url, pool_size=5)
        self._session_factory = create_session_factory(self._db_engine)
        self._session = self._session_factory()

        # Services
        self._property_service = PropertyService(self._session)
        self._run_service = ScraperRunService(self._session)

        # MinIO
        self._minio = MinioStorageClient()
        await self._minio.ensure_bucket()

        # Track run
        self._run_id = str(uuid.uuid4())
        self.logger = get_logger(
            portal=self.PORTAL_SOURCE,
            scraper_id=self._scraper_id,
            run_id=self._run_id,
        )

        if self._run_service:
            run = await self._run_service.create_run(
                portal_source=self.PORTAL_SOURCE,
                scraper_id=self._scraper_id,
            )
            self._run_id = run.id
            self.logger.info(
                "Spider opened",
                extra={"run_id": self._run_id, "portal": self.PORTAL_SOURCE},
            )

    async def close_spider(self, spider: Any) -> None:  # noqa: ANN401
        """Clean up connections when the spider closes.

        Flushes pending operations, records run completion, emits final
        metrics, and closes the database session.

        Args:
            spider: The Scrapy ``Spider`` instance (unused, enables override).

        """
        duration = time.monotonic() - self._start_time

        # Record run completion
        if self._run_service and self._run_id:
            await self._run_service.complete_run(
                run_id=self._run_id,
                listings_scraped=self._items_scraped,
                listings_new=self._items_new,
                listings_updated=self._items_updated,
                errors_count=self._errors,
            )

        # Emit metrics
        from scraper_base.metrics import observe_scrape_duration  # noqa: PLC0415

        observe_scrape_duration(self.PORTAL_SOURCE, duration)
        if self._property_service:
            count = await self._property_service.count_active(self.PORTAL_SOURCE)
            set_active_listings(self.PORTAL_SOURCE, count)

        self.logger.info(
            "Spider closed",
            extra={
                "duration_s": round(duration, 2),
                "items_scraped": self._items_scraped,
                "items_new": self._items_new,
                "items_updated": self._items_updated,
                "errors": self._errors,
            },
        )

        # Clean up
        if self._session:
            await self._session.close()
        if self._db_engine:
            await self._db_engine.dispose()

    async def process_item(
        self,
        item: Any,  # noqa: ANN401
        spider: Any,  # noqa: ANN401
    ) -> dict[str, Any]:
        """Process a single scraped item.

        Validates, persists, and emits metrics for the item.

        Args:
            item: The raw Scrapy item.
            spider: The Scrapy ``Spider`` instance.

        Returns:
            The processed item dictionary (passed through to Scrapy).

        """
        try:
            data = self.item_to_data(item)
            data.setdefault("portal_source", self.PORTAL_SOURCE)

            start = time.monotonic()
            if self._property_service is None:
                msg = "PropertyService not initialised — open_spider() may not have been called"
                raise RuntimeError(msg)
            _, is_new = await self._property_service.upsert_property(data)
            duration = time.monotonic() - start

            # Metrics
            observe_db_write("insert" if is_new else "update", duration)
            increment_listings_scraped(
                portal=self.PORTAL_SOURCE,
                city=data.get("city", "unknown"),
                property_type=data.get("property_type", "unknown"),
            )

            self._items_scraped += 1
            if is_new:
                self._items_new += 1
            else:
                self._items_updated += 1

            return dict(item) if hasattr(item, "__iter__") else {"source_id": data.get("source_id")}

        except Exception:
            self._errors += 1
            increment_errors(self.PORTAL_SOURCE, error_type="processing")
            self.logger.exception("Failed to process item")
            raise


def _check_portal_source(value: str) -> None:
    """Validate that ``PORTAL_SOURCE`` is set to a non-default value."""
    if value == "unknown":
        msg = "BasePipeline subclasses must set PORTAL_SOURCE to a non-empty string (e.g. 'otodom')."
        raise AttributeError(msg)
