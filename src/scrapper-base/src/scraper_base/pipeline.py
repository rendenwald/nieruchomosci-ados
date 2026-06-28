"""
BasePipeline — abstract base class for Scrapy pipelines.

All portal-specific scrapers subclass ``BasePipeline`` and implement the
``item_to_data()`` method. The base class handles database connectivity,
metrics auto-emission, structured logging, and MinIO storage.
"""

import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import httpx

from scraper_base.database import (
    create_async_engine,
    create_session_factory,
    wait_for_db,
)
from scraper_base.logging_config import get_logger
from scraper_base.metrics import (
    increment_errors,
    increment_listings_scraped,
    observe_db_write,
    push_metrics,
    scraper_last_run_timestamp,
    set_active_listings,
)
from scraper_base.services import PropertyService, ScraperRunService
from scraper_base.storage import MAX_PHOTOS_PER_PROPERTY, MinioStorageClient

if TYPE_CHECKING:
    from scrapy import Spider  # noqa: TC004  # Imported only for type hints


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
    # Photo processing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_photo_urls(data: dict[str, Any]) -> list[str]:
        """Extract photo URLs from a property data dict.

        Looks for a ``photos`` key containing a list of dicts with a
        ``url`` key, or a list of plain URL strings.

        Args:
            data: The property data dict from ``item_to_data()``.

        Returns:
            A list of photo URL strings (max ``MAX_PHOTOS_PER_PROPERTY``).

        """
        raw = data.get("photos")
        if not raw:
            return []
        if isinstance(raw, list):
            urls: list[str] = []
            for entry in raw[:MAX_PHOTOS_PER_PROPERTY]:
                if isinstance(entry, str):
                    urls.append(entry)
                elif isinstance(entry, dict):
                    url = entry.get("url")
                    if isinstance(url, str):
                        urls.append(url)
            return urls
        return []

    async def _process_photos(
        self,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Download photos from URLs and upload them to MinIO.

        Args:
            data: The property data dict with optional ``photos`` key.

        Returns:
            A list of photo metadata dicts with MinIO ``path``, original
            ``url``, and ``order`` keys. Empty list if no photos or MinIO
            unavailable.

        """
        if self._minio is None or not self._minio.is_available:
            self.logger.debug("MinIO unavailable, skipping photo upload")
            return []

        photo_urls = self._extract_photo_urls(data)
        if not photo_urls:
            return []

        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for url in photo_urls:
                try:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    object_name = await self._minio.upload_photo(response.content)
                    if object_name:
                        # Generate and upload thumbnail (non-blocking on failure)
                        thumbnail_name = await self._minio.upload_thumbnail(response.content)
                        photo_entry: dict[str, Any] = {
                            "path": object_name,
                            "url": url,
                            "order": len(results) + 1,
                        }
                        if thumbnail_name:
                            photo_entry["thumbnail_path"] = thumbnail_name
                        results.append(photo_entry)
                        self.logger.debug(
                            "Photo uploaded to MinIO",
                            url=url,
                            object_name=object_name,
                        )
                except httpx.HTTPStatusError as exc:
                    self.logger.warning(
                        "Photo download HTTP error",
                        url=url,
                        status_code=exc.response.status_code,
                    )
                except httpx.RequestError as exc:
                    self.logger.warning(
                        "Photo download request failed",
                        url=url,
                        error=str(exc),
                    )
                except Exception:  # noqa: BLE001
                    self.logger.exception(
                        "Photo processing failed",
                        url=url,
                    )

        if results:
            self.logger.info(
                "Photos stored in MinIO",
                count=len(results),
                total_urls=len(photo_urls),
            )

        return results

    # ------------------------------------------------------------------
    # Spider lifecycle
    # ------------------------------------------------------------------

    async def open_spider(self, spider: "Spider | Any" = None) -> None:
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
        await wait_for_db(self._db_engine)
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
                run_id=self._run_id,
                portal=self.PORTAL_SOURCE,
            )

    async def close_spider(self, spider: "Spider | Any" = None) -> None:
        """Clean up connections when the spider closes.

        Flushes pending operations, records run completion, emits final
        metrics, pushes metrics to Prometheus Pushgateway, and closes
        the database session.

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
            duration_s=round(duration, 2),
            items_scraped=self._items_scraped,
            items_new=self._items_new,
            items_updated=self._items_updated,
            errors=self._errors,
        )

        # ── Push metrics to Prometheus Pushgateway ──────────────────────
        scraper_last_run_timestamp.labels(portal=self.PORTAL_SOURCE).set(
            time.time(),
        )
        pushgateway_url = os.environ.get(
            "PUSHGATEWAY_URL",
            "http://pushgateway:9091",
        )
        try:
            push_metrics(pushgateway_url, self.PORTAL_SOURCE)
            self.logger.info(
                "Metrics pushed to Pushgateway",
                pushgateway_url=pushgateway_url,
                portal=self.PORTAL_SOURCE,
            )
        except Exception:
            self.logger.warning(
                "Failed to push metrics to Pushgateway",
                pushgateway_url=pushgateway_url,
                portal=self.PORTAL_SOURCE,
                exc_info=True,
            )

        # Clean up
        if self._session:
            await self._session.close()
        if self._db_engine:
            await self._db_engine.dispose()

    async def process_item(
        self,
        item: Any,
        spider: "Spider | Any" = None,
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

            # Download photos and store in MinIO (non-blocking on failure)
            if data.get("photos"):
                photo_results = await self._process_photos(data)
                if photo_results and self._property_service is not None:
                    await self._property_service.update_photos(
                        source_id=data["source_id"],
                        portal_source=data["portal_source"],
                        photos=photo_results,
                    )

            # Pass through to Scrapy: convert dicts, leave Scrapy Items as-is
            if isinstance(item, dict):
                return item
            return {"source_id": data.get("source_id")}

        except Exception:
            self._errors += 1
            increment_errors(self.PORTAL_SOURCE, error_type="processing")
            self.logger.exception("Failed to process item")
            raise


def _check_portal_source(value: str) -> None:
    """Validate that ``PORTAL_SOURCE`` is set to a non-default value."""
    if not value or value == "unknown":
        msg = "BasePipeline subclasses must set PORTAL_SOURCE to a non-empty string (e.g. 'otodom')."
        raise AttributeError(msg)
