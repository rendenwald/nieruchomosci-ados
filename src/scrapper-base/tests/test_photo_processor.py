"""Tests for BasePipeline photo processing."""
# ruff: noqa: S108 — test URLs are safe

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scraper_base.pipeline import BasePipeline
from scraper_base.storage import MAX_PHOTOS_PER_PROPERTY


class MinimalPipelineForTest(BasePipeline):  # noqa: N801
    """Concrete subclass for testing — not collected by pytest."""

    __test__ = False
    PORTAL_SOURCE = "test-portal"

    def item_to_data(self, item: dict) -> dict:
        """Convert test item to property data dict."""
        return {
            "portal_source": self.PORTAL_SOURCE,
            "source_id": item.get("source_id", "TEST-001"),
            "title": item.get("title", "Test property"),
            "price": item.get("price", 100000),
            "city": item.get("city", "Test City"),
            "property_type": item.get("property_type", "apartment"),
            "photos": item.get("photos", []),
        }


class TestExtractPhotoUrls:
    """_extract_photo_urls static method."""

    def test_extracts_from_list_of_dicts(self):
        """Extracts URLs from a list of dicts with 'url' keys."""
        data = {"photos": [{"url": "https://example.com/1.jpg"}, {"url": "https://example.com/2.jpg"}]}
        result = BasePipeline._extract_photo_urls(data)
        assert result == ["https://example.com/1.jpg", "https://example.com/2.jpg"]

    def test_extracts_from_list_of_strings(self):
        """Extracts URLs from a list of plain URL strings."""
        data = {"photos": ["https://example.com/1.jpg", "https://example.com/2.jpg"]}
        result = BasePipeline._extract_photo_urls(data)
        assert result == ["https://example.com/1.jpg", "https://example.com/2.jpg"]

    def test_returns_empty_for_missing_key(self):
        """Returns empty list when photos key is missing."""
        assert BasePipeline._extract_photo_urls({}) == []

    def test_returns_empty_for_none(self):
        """Returns empty list when photos is None."""
        assert BasePipeline._extract_photo_urls({"photos": None}) == []

    def test_returns_empty_for_empty_list(self):
        """Returns empty list when photos is empty."""
        assert BasePipeline._extract_photo_urls({"photos": []}) == []

    def test_returns_empty_for_non_list(self):
        """Returns empty list when photos is not a list."""
        assert BasePipeline._extract_photo_urls({"photos": "invalid"}) == []

    def test_enforces_max_photos(self):
        """Returns at most MAX_PHOTOS_PER_PROPERTY URLs."""
        many_urls = [{"url": f"https://example.com/{i}.jpg"} for i in range(50)]
        result = BasePipeline._extract_photo_urls({"photos": many_urls})
        assert len(result) == MAX_PHOTOS_PER_PROPERTY
        assert result == [f"https://example.com/{i}.jpg" for i in range(MAX_PHOTOS_PER_PROPERTY)]

    def test_skips_dicts_without_url_key(self):
        """Skips entries in list that are dicts without 'url' key."""
        data = {"photos": [{"url": "https://example.com/1.jpg"}, {"title": "not a photo"}]}
        result = BasePipeline._extract_photo_urls(data)
        assert result == ["https://example.com/1.jpg"]

    def test_skips_non_string_url_values(self):
        """Skips entries where url value is not a string."""
        data = {"photos": [{"url": "https://example.com/1.jpg"}, {"url": 123}]}
        result = BasePipeline._extract_photo_urls(data)
        assert result == ["https://example.com/1.jpg"]


class TestProcessPhotos:
    """_process_photos instance method."""

    @pytest.fixture
    def pipeline(self):
        """Return a pipeline with a mock MinIO client."""
        pipeline = MinimalPipelineForTest()

        mock_minio = MagicMock()
        mock_minio.is_available = True
        def _fake_upload(data: bytes, object_name: str | None = None) -> str:
            import hashlib  # noqa: PLC0415
            return f"photos/ab/cd/{hashlib.sha256(data).hexdigest()}.jpg"

        mock_minio.upload_photo = AsyncMock(side_effect=_fake_upload)
        pipeline._minio = mock_minio
        return pipeline

    @pytest.fixture
    def pipeline_no_minio(self):
        """Return a pipeline with MinIO unavailable."""
        pipeline = MinimalPipelineForTest()
        pipeline._minio = None
        return pipeline

    async def test_uploads_photos(self, pipeline):
        """Downloads photos and uploads to MinIO, returning metadata."""
        fake_bytes = b"fake-image-bytes-1"

        async def mock_get(url, follow_redirects=True):
            return MagicMock(
                content=fake_bytes,
                raise_for_status=lambda: None,
            )

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data = {"photos": [{"url": "https://example.com/1.jpg"}, {"url": "https://example.com/2.jpg"}]}
            results = await pipeline._process_photos(data)

        assert len(results) == 2
        assert results[0]["url"] == "https://example.com/1.jpg"
        assert results[0]["order"] == 1
        assert results[1]["url"] == "https://example.com/2.jpg"
        assert results[1]["order"] == 2
        assert results[0]["path"].startswith("photos/")
        assert results[1]["path"].startswith("photos/")

    async def test_returns_empty_when_no_photos(self, pipeline):
        """Returns empty list when data has no photos."""
        results = await pipeline._process_photos({"no_photos": True})
        assert results == []

    async def test_returns_empty_when_minio_unavailable(self, pipeline_no_minio):
        """Returns empty list when MinIO is unavailable."""
        data = {"photos": [{"url": "https://example.com/1.jpg"}]}
        results = await pipeline_no_minio._process_photos(data)
        assert results == []

    async def test_handles_http_error(self, pipeline):
        """Continues processing remaining photos on HTTP error."""
        async def mock_get(url, follow_redirects=True):
            if "1.jpg" in url:
                resp = MagicMock()
                resp.status_code = 404
                raise httpx.HTTPStatusError("Not found", request=MagicMock(), response=resp)
            return MagicMock(content=b"ok", raise_for_status=lambda: None)

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data = {"photos": [{"url": "https://example.com/1.jpg"}, {"url": "https://example.com/2.jpg"}]}
            results = await pipeline._process_photos(data)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/2.jpg"

    async def test_handles_request_error(self, pipeline):
        """Continues processing remaining photos on network error."""
        async def mock_get(url, follow_redirects=True):
            if "1.jpg" in url:
                raise httpx.RequestError("Connection refused")
            return MagicMock(content=b"ok", raise_for_status=lambda: None)

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data = {"photos": [{"url": "https://example.com/1.jpg"}, {"url": "https://example.com/2.jpg"}]}
            results = await pipeline._process_photos(data)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/2.jpg"


class TestProcessItemPhotoIntegration:
    """process_item integration with photo processing."""

    async def test_process_item_with_photos(
        self,
        db_session,
        monkeypatch,
        mock_minio,
    ):
        """process_item uploads photos and updates the property."""
        monkeypatch.setenv("MINIO_ENDPOINT", "minio.example.com:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "testkey")
        monkeypatch.setenv("MINIO_SECRET_KEY", "testsecret")

        from scraper_base.services import PropertyService  # noqa: PLC0415

        pipeline = MinimalPipelineForTest()
        pipeline._session = db_session
        pipeline._property_service = PropertyService(db_session)
        pipeline._minio = mock_minio

        # Mock httpx to return fake photo bytes
        fake_bytes = b"fake-image-bytes-integration"

        async def mock_get(url, follow_redirects=True):
            return MagicMock(content=fake_bytes, raise_for_status=lambda: None)

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            item = {
                "source_id": "PHOTO-001",
                "title": "With photos",
                "city": "Gdańsk",
                "price": 450000,
                "photos": [{"url": "https://example.com/1.jpg"}],
            }
            result = await pipeline.process_item(item, None)

        assert pipeline._items_scraped == 1
        assert result is not None
        assert result.get("source_id") == "PHOTO-001"

        # Verify photos were stored in the property
        prop = await pipeline._property_service.get_by_source(
            pipeline.PORTAL_SOURCE,
            "PHOTO-001",
        )
        assert prop is not None
        assert prop.photos is not None
        if isinstance(prop.photos, list):
            assert len(prop.photos) >= 1
            assert prop.photos[0]["url"] == "https://example.com/1.jpg"
            assert "path" in prop.photos[0]
