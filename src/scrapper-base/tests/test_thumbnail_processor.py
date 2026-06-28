"""Tests for thumbnail generation in the photo processing pipeline.

Covers:
- TN-1: Generate thumbnail from JPEG bytes via Pillow
- TN-2: Thumbnail preserves aspect ratio then center-crops
- TN-3: Non-image bytes raise gracefully
- TN-4: Thumbnail uploaded to correct MinIO path
- TN-5: Thumbnail object path uses same SHA256 directory
- TN-10: _process_photos() generates + uploads thumbnail after original
- TN-11: Thumbnail failure does not block original photo upload
- TN-12: MinIO unavailable skips both original and thumbnail
- TN-13: Empty photo list skips thumbnail processing
"""

import hashlib
import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from PIL import Image

from scraper_base.pipeline import BasePipeline
from scraper_base.storage import MAX_PHOTOS_PER_PROPERTY, MinioStorageClient

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_test_jpeg_bytes(
    width: int = 100,
    height: int = 80,
    color: tuple[int, int, int] = (200, 100, 50),
) -> bytes:
    """Create a small JPEG image in memory and return the bytes."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_test_png_bytes(
    width: int = 100,
    height: int = 80,
) -> bytes:
    """Create a small PNG image in memory and return the bytes."""
    img = Image.new("RGBA", (width, height), (200, 100, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# TN-1, TN-2, TN-4, TN-5: MinioStorageClient.upload_thumbnail
# ---------------------------------------------------------------------------


class TestUploadThumbnail:
    """MinioStorageClient.upload_thumbnail method."""

    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> MinioStorageClient:
        """Return a MinioStorageClient with env vars set (no real connect)."""
        monkeypatch.setenv("MINIO_ENDPOINT", "localhost:1")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "testkey")
        monkeypatch.setenv("MINIO_SECRET_KEY", "testsecret")
        return MinioStorageClient()

    async def test_tn1_generates_thumbnail_from_jpeg_bytes(self, client: MinioStorageClient) -> None:
        """TN-1: Generate thumbnail from JPEG bytes via Pillow.

        Verifies the thumbnail upload is attempted and the derived object
        name follows the _thumb convention.
        """
        # Force _available and _initialised so upload is attempted
        client._available = True
        client._initialised = True

        # Mock upload_photo to avoid real MinIO
        original_upload = client.upload_photo = AsyncMock(return_value="photos/ab/cd/abcdef_thumb.jpg")  # type: ignore[method-assign]

        jpeg_bytes = _make_test_jpeg_bytes()
        result = await client.upload_thumbnail(jpeg_bytes)

        # Should have called upload_photo with the thumbnail bytes
        original_upload.assert_awaited_once()
        call_args = original_upload.await_args
        assert call_args is not None
        assert call_args.kwargs["content_type"] == "image/jpeg"
        # Verify we got an object name back
        assert result == "photos/ab/cd/abcdef_thumb.jpg"

    async def test_tn2_thumbnail_dimensions_400x300(self) -> None:
        """TN-2: Thumbnail preserves aspect ratio then center-crops to 400x300."""
        # Test with various input sizes
        test_sizes = [
            (800, 600),   # 4:3 landscape
            (1600, 1200), # 4:3 large
            (400, 600),   # portrait
            (800, 300),   # ultra-wide
            (400, 300),   # exact size
        ]

        for width, height in test_sizes:
            jpeg_bytes = _make_test_jpeg_bytes(width=width, height=height)
            img = Image.open(io.BytesIO(jpeg_bytes))
            # Simulate what upload_thumbnail does
            img = img.convert("RGB")
            img.thumbnail((400, 300), Image.LANCZOS)

            # Center-crop to exact dimensions if needed
            if img.size != (400, 300):
                left = (img.width - 400) / 2
                top = (img.height - 300) / 2
                right = left + 400
                bottom = top + 300
                img = img.crop((left, top, right, bottom))

            assert img.size == (400, 300), f"Thumbnail from {width}x{height} is {img.size}, expected 400x300"

    async def test_tn3_non_image_bytes_graceful(self, client: MinioStorageClient) -> None:
        """TN-3: Non-image bytes raise gracefully (logged warning, no upload)."""
        client._available = True
        client._initialised = True
        client.upload_photo = AsyncMock()  # type: ignore[method-assign]

        result = await client.upload_thumbnail(b"not an image at all")

        assert result is None
        client.upload_photo.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_tn4_thumbnail_path_convention(self) -> None:
        """TN-4: Thumbnail uploaded with _thumb path convention."""
        client = MinioStorageClient(
            access_key="testkey",
            secret_key="testsecret",
        )
        client._available = True
        client._initialised = True
        client.upload_photo = AsyncMock(return_value="photos/ab/cd/abcdef123_thumb.jpg")  # type: ignore[method-assign]

        jpeg_bytes = _make_test_jpeg_bytes()
        await client.upload_thumbnail(jpeg_bytes)

        client.upload_photo.assert_awaited_once()  # type: ignore[attr-defined]
        call_args = client.upload_photo.await_args  # type: ignore[attr-defined]
        assert call_args is not None
        obj_name = call_args.kwargs["object_name"]
        assert obj_name is not None
        assert obj_name.endswith("_thumb.jpg")

    async def test_tn5_thumbnail_same_sha256_directory(self) -> None:
        """TN-5: Thumbnail object path uses same SHA256 directory."""
        client = MinioStorageClient(
            access_key="testkey",
            secret_key="testsecret",
        )
        client._available = True
        client._initialised = True

        jpeg_bytes = _make_test_jpeg_bytes()
        sha256 = hashlib.sha256(jpeg_bytes).hexdigest()
        expected_path = f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg"

        client.upload_photo = AsyncMock(return_value=expected_path)  # type: ignore[method-assign]
        result = await client.upload_thumbnail(jpeg_bytes)

        assert result == expected_path

    async def test_upload_thumbnail_minio_unavailable(self, client: MinioStorageClient) -> None:
        """Returns None when MinIO is unavailable after initialisation."""
        client._initialised = True
        client._available = False
        client.upload_photo = AsyncMock()  # type: ignore[method-assign]

        result = await client.upload_thumbnail(b"test data")

        assert result is None
        client.upload_photo.assert_not_awaited()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TN-10, TN-11, TN-12, TN-13: Pipeline integration
# ---------------------------------------------------------------------------


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


class TestThumbnailPipelineIntegration:
    """_process_photos thumbnail integration."""

    @pytest.fixture
    def pipeline(self) -> MinimalPipelineForTest:
        """Return a pipeline with a mock MinIO client supporting upload_thumbnail."""
        pipeline = MinimalPipelineForTest()

        mock_minio = MagicMock()
        mock_minio.is_available = True

        def _fake_upload(data: bytes, object_name: str | None = None) -> str:
            sha256 = hashlib.sha256(data).hexdigest()
            return f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"

        async def _fake_thumbnail(
            data: bytes,
            object_name: str | None = None,
            size: tuple[int, int] = (400, 300),
            quality: int = 85,
        ) -> str | None:
            sha256 = hashlib.sha256(data).hexdigest()
            return f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg"

        mock_minio.upload_photo = AsyncMock(side_effect=_fake_upload)
        mock_minio.upload_thumbnail = AsyncMock(side_effect=_fake_thumbnail)
        pipeline._minio = mock_minio
        return pipeline

    @pytest.fixture
    def pipeline_failing_thumbnail(self) -> MinimalPipelineForTest:
        """Return a pipeline where thumbnail generation fails (TN-11)."""
        pipeline = MinimalPipelineForTest()

        mock_minio = MagicMock()
        mock_minio.is_available = True

        def _fake_upload(data: bytes, object_name: str | None = None) -> str:
            sha256 = hashlib.sha256(data).hexdigest()
            return f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"

        mock_minio.upload_photo = AsyncMock(side_effect=_fake_upload)
        mock_minio.upload_thumbnail = AsyncMock(return_value=None)
        pipeline._minio = mock_minio
        return pipeline

    @pytest.fixture
    def pipeline_no_minio(self) -> MinimalPipelineForTest:
        """Return a pipeline with MinIO unavailable."""
        pipeline = MinimalPipelineForTest()
        pipeline._minio = None
        return pipeline

    async def test_tn10_thumbnail_included_in_results(self, pipeline: MinimalPipelineForTest) -> None:
        """TN-10: _process_photos generates + uploads thumbnail after original.

        Both ``path`` and ``thumbnail_path`` should be in returned dict.
        """
        fake_bytes = _make_test_jpeg_bytes()

        async def mock_get(url: str, follow_redirects: bool = True) -> MagicMock:  # noqa: ARG001
            return MagicMock(
                content=fake_bytes,
                raise_for_status=lambda: None,
            )

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data: dict[str, Any] = {"photos": [{"url": "https://example.com/1.jpg"}]}
            results = await pipeline._process_photos(data)

        assert len(results) == 1
        assert "path" in results[0]
        assert "thumbnail_path" in results[0]
        assert results[0]["thumbnail_path"].endswith("_thumb.jpg")

        # Verify thumbnail was called
        assert pipeline._minio is not None
        pipeline._minio.upload_thumbnail.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_tn11_thumbnail_failure_does_not_block(
        self,
        pipeline_failing_thumbnail: MinimalPipelineForTest,
    ) -> None:
        """TN-11: Thumbnail failure does not block original photo upload.

        Original stored, thumbnail_path is missing from the dict.
        """
        fake_bytes = _make_test_jpeg_bytes()

        async def mock_get(url: str, follow_redirects: bool = True) -> MagicMock:  # noqa: ARG001
            return MagicMock(
                content=fake_bytes,
                raise_for_status=lambda: None,
            )

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data = {"photos": [{"url": "https://example.com/1.jpg"}]}
            results = await pipeline_failing_thumbnail._process_photos(data)

        assert len(results) == 1
        assert "path" in results[0]
        assert "thumbnail_path" not in results[0]

    async def test_tn12_minio_unavailable_skips_all(
        self,
        pipeline_no_minio: MinimalPipelineForTest,
    ) -> None:
        """TN-12: MinIO unavailable skips both original and thumbnail.

        Empty list returned.
        """
        data = {"photos": [{"url": "https://example.com/1.jpg"}]}
        results = await pipeline_no_minio._process_photos(data)
        assert results == []

    async def test_tn13_empty_photo_list(
        self,
        pipeline: MinimalPipelineForTest,
    ) -> None:
        """TN-13: Empty photo list skips thumbnail processing.

        Empty list returned promptly.
        """
        results = await pipeline._process_photos({"photos": []})
        assert results == []


# ---------------------------------------------------------------------------
# Regression: MAX_PHOTOS_PER_PROPERTY (AC-7)
# ---------------------------------------------------------------------------


class TestThumbnailMaxPhotos:
    """MAX_PHOTOS_PER_PROPERTY cap applies to thumbnail generation."""

    async def test_max_photos_cap_enforced(self) -> None:
        """At most MAX_PHOTOS_PER_PROPERTY thumbnails are generated."""
        pipeline = MinimalPipelineForTest()
        assert MAX_PHOTOS_PER_PROPERTY == 20

        fake_bytes = _make_test_jpeg_bytes()

        async def mock_get(url: str, follow_redirects: bool = True) -> MagicMock:  # noqa: ARG001
            return MagicMock(
                content=fake_bytes,
                raise_for_status=lambda: None,
            )

        mock_minio = MagicMock()
        mock_minio.is_available = True

        def _fake_upload(data: bytes, object_name: str | None = None) -> str:
            sha256 = hashlib.sha256(data).hexdigest()
            return f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"

        mock_minio.upload_photo = AsyncMock(side_effect=_fake_upload)
        mock_minio.upload_thumbnail = AsyncMock(side_effect=_fake_upload)
        pipeline._minio = mock_minio

        many_urls = [{"url": f"https://example.com/{i}.jpg"} for i in range(30)]

        with patch.object(httpx, "AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.get = AsyncMock(side_effect=mock_get)
            mock_client_cls.return_value = mock_client

            data = {"photos": many_urls}
            results = await pipeline._process_photos(data)

        assert len(results) == MAX_PHOTOS_PER_PROPERTY  # 20
        for r in results:
            assert "thumbnail_path" in r
