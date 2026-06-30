"""
Endpoint tests for ``POST /api/v1/photos/upload``.

Tests cover:
- UP-1 through UP-8: Upload endpoint validation
- DD-1, DD-2: Deduplication
- TN-1, TN-2: Thumbnail generation
- EH-1, EH-2: Error handling

The service layer (``process_upload``) is mocked to isolate HTTP-layer behaviour
(response codes, headers, error formatting).
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from app.services.photo_upload_service import (
    PhotoUploadError,
    PhotoValidationError,
    UploadResult,
)

SAMPLE_RESULT = UploadResult(
    sha256="ab" + "c" * 62,
    photo_url="/api/v1/photos/" + "ab" + "c" * 62 + ".jpg",
    thumbnail_url="/api/v1/photos/" + "ab" + "c" * 62 + "/thumb.jpg",
    width=2048,
    height=1536,
    file_size_bytes=524288,
    mime_type="image/jpeg",
)


# ---------------------------------------------------------------------------
# UP — Upload Endpoint
# ---------------------------------------------------------------------------


class TestUploadEndpointUP:
    """UP-1 through UP-8: Upload endpoint validation."""

    async def test_up1_valid_jpeg_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-1: Valid JPEG upload returns 201 with correct fields."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(return_value=SAMPLE_RESULT),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.jpg", b"fake-jpeg-data", "image/jpeg")},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["sha256"] == SAMPLE_RESULT.sha256
        assert body["photo_url"] == SAMPLE_RESULT.photo_url
        assert body["thumbnail_url"] == SAMPLE_RESULT.thumbnail_url
        assert body["width"] == SAMPLE_RESULT.width
        assert body["height"] == SAMPLE_RESULT.height
        assert body["file_size_bytes"] == SAMPLE_RESULT.file_size_bytes
        assert body["mime_type"] == SAMPLE_RESULT.mime_type

    async def test_up2_valid_png_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-2: Valid PNG upload returns 201."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(return_value=SAMPLE_RESULT),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.png", b"fake-png-data", "image/png")},
            )
        assert response.status_code == 201

    async def test_up3_valid_webp_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-3: Valid WebP upload returns 201."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(return_value=SAMPLE_RESULT),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.webp", b"fake-webp-data", "image/webp")},
            )
        assert response.status_code == 201

    async def test_up4_invalid_pdf_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-4: Invalid file type (PDF) returns 422."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(
                side_effect=PhotoValidationError(
                    "Invalid file type 'application/pdf'. Allowed: image/jpeg, image/png, image/webp",
                ),
            ),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
            )
        assert response.status_code == 422
        assert "Invalid file type" in response.json()["detail"]

    async def test_up5_invalid_gif_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-5: Invalid file type (GIF) returns 422."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(
                side_effect=PhotoValidationError(
                    "Invalid file type 'image/gif'. Allowed: image/jpeg, image/png, image/webp",
                ),
            ),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.gif", b"GIF89a", "image/gif")},
            )
        assert response.status_code == 422
        assert "Invalid file type" in response.json()["detail"]

    async def test_up6_oversized_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-6: File exceeding size limit returns 422."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(
                side_effect=PhotoValidationError(
                    "File size 20971520 bytes exceeds maximum 10485760 bytes",
                ),
            ),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("large.jpg", b"x" * (20 * 1024 * 1024), "image/jpeg")},
            )
        assert response.status_code == 422
        assert "exceeds maximum" in response.json()["detail"]

    async def test_up7_missing_file_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-7: Missing file field returns 422."""
        response = await client.post("/api/v1/photos/upload")
        assert response.status_code == 422
        # FastAPI returns 422 for missing required File(...) parameter
        assert "detail" in response.json()

    async def test_up8_empty_file_in_endpoint(
        self,
        client: AsyncClient,
    ) -> None:
        """UP-8: Empty file returns 422 from the endpoint itself."""
        # The endpoint checks for empty data before calling process_upload
        response = await client.post(
            "/api/v1/photos/upload",
            files={"file": ("empty.jpg", b"", "image/jpeg")},
        )
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DD — Deduplication (via mocked service)
# ---------------------------------------------------------------------------


class TestUploadDedupDD:
    """DD-1, DD-2: Dedup via the mocked service."""

    async def test_dd1_same_sha256_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        """DD-1: Same bytes uploaded twice should succeed both times (no error).

        The service handles dedup transparently, returning existing metadata.
        Both calls return 201.
        """
        result = UploadResult(
            sha256="aa" + "b" * 62,
            photo_url="/api/v1/photos/" + "aa" + "b" * 62 + ".jpg",
            thumbnail_url="/api/v1/photos/" + "aa" + "b" * 62 + "/thumb.jpg",
            width=800,
            height=600,
            file_size_bytes=3000,
            mime_type="image/jpeg",
        )
        mock_fn = AsyncMock(return_value=result)

        with patch("app.routers.photos.process_upload", new=mock_fn):
            # First upload
            resp1 = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("img.jpg", b"same-data", "image/jpeg")},
            )
            # Second upload with same bytes
            resp2 = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("img.jpg", b"same-data", "image/jpeg")},
            )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["sha256"] == resp2.json()["sha256"]
        # process_upload should have been called twice (mocked)
        assert mock_fn.call_count == 2

    async def test_dd2_different_bytes_different_shas(
        self,
        client: AsyncClient,
    ) -> None:
        """DD-2: Different images produce different sha256 values."""
        result_a = UploadResult(
            sha256="a" * 64,
            photo_url="/api/v1/photos/" + "a" * 64 + ".jpg",
            thumbnail_url="/api/v1/photos/" + "a" * 64 + "/thumb.jpg",
            width=800,
            height=600,
            file_size_bytes=3000,
            mime_type="image/jpeg",
        )
        result_b = UploadResult(
            sha256="b" * 64,
            photo_url="/api/v1/photos/" + "b" * 64 + ".jpg",
            thumbnail_url="/api/v1/photos/" + "b" * 64 + "/thumb.jpg",
            width=1024,
            height=768,
            file_size_bytes=4000,
            mime_type="image/jpeg",
        )

        call_count = 0

        async def mock_process(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return result_a if call_count == 1 else result_b

        with patch("app.routers.photos.process_upload", new=mock_process):
            resp1 = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("img1.jpg", b"data-a", "image/jpeg")},
            )
            resp2 = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("img2.jpg", b"data-b", "image/jpeg")},
            )

        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["sha256"] != resp2.json()["sha256"]


# ---------------------------------------------------------------------------
# TN — Thumbnail
# ---------------------------------------------------------------------------


class TestUploadThumbnailTN:
    """TN-1, TN-2: Thumbnail generation paths."""

    async def test_tn1_thumbnail_in_response(
        self,
        client: AsyncClient,
    ) -> None:
        """TN-1: thumbnail_url present in response."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(return_value=SAMPLE_RESULT),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.jpg", b"data", "image/jpeg")},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["thumbnail_url"] == SAMPLE_RESULT.thumbnail_url

    async def test_tn2_thumbnail_path_format(
        self,
        client: AsyncClient,
    ) -> None:
        """TN-2: thumbnail_url follows /api/v1/photos/{sha256}/thumb.jpg."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(return_value=SAMPLE_RESULT),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.jpg", b"data", "image/jpeg")},
            )
        assert response.status_code == 201
        thumb_url = response.json()["thumbnail_url"]
        sha256 = SAMPLE_RESULT.sha256
        assert f"/api/v1/photos/{sha256}/thumb.jpg" == thumb_url


# ---------------------------------------------------------------------------
# EH — Error Handling
# ---------------------------------------------------------------------------


class TestUploadErrorHandlingEH:
    """EH-1, EH-2: Error responses."""

    async def test_eh1_validation_error_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """EH-1: PhotoValidationError maps to 422."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(
                side_effect=PhotoValidationError("Invalid file type"),
            ),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.jpg", b"data", "image/jpeg")},
            )
        assert response.status_code == 422
        assert "Invalid file type" in response.json()["detail"]

    async def test_eh2_upload_error_returns_503(
        self,
        client: AsyncClient,
    ) -> None:
        """EH-2: PhotoUploadError maps to 503."""
        with patch(
            "app.routers.photos.process_upload",
            new=AsyncMock(
                side_effect=PhotoUploadError("Photo storage temporarily unavailable"),
            ),
        ):
            response = await client.post(
                "/api/v1/photos/upload",
                files={"file": ("test.jpg", b"data", "image/jpeg")},
            )
        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]
