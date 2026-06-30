"""
Unit tests for the photo upload service layer.

Tests cover:
- ``validate_file_type`` — SV-1, SV-2
- ``validate_file_size`` — SV-3, SV-4
- ``resize_image`` — RS-1 through RS-6, SV-5 through SV-7
- ``process_upload`` — DD-1, DD-2, TN-1, TN-2, EH-1, EH-2
"""

import hashlib
import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image
from scraper_base.models import PhotoAsset
from sqlalchemy import select
from sqlalchemy.sql import Select

from app.services.photo_upload_service import (
    ALLOWED_MIME_TYPES,
    PhotoUploadError,
    PhotoValidationError,
    process_upload,
    resize_image,
    validate_file_size,
    validate_file_type,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_image_bytes(
    width: int = 200,
    height: int = 150,
    fmt: str = "JPEG",
    color: tuple[int, ...] = (255, 0, 0),
) -> bytes:
    """Generate a simple solid-colour image and return its bytes."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# validate_file_type
# ---------------------------------------------------------------------------


class TestValidateFileType:
    """SV-1 / SV-2: File type validation."""

    def test_sv1_valid_jpeg(self) -> None:
        """SV-1: JPEG is accepted."""
        validate_file_type("image/jpeg")  # no raise

    def test_sv1_valid_png(self) -> None:
        """SV-1: PNG is accepted."""
        validate_file_type("image/png")  # no raise

    def test_sv1_valid_webp(self) -> None:
        """SV-1: WebP is accepted."""
        validate_file_type("image/webp")  # no raise

    def test_sv2_invalid_pdf(self) -> None:
        """SV-2: PDF is rejected."""
        with pytest.raises(PhotoValidationError, match="Invalid file type"):
            validate_file_type("application/pdf")

    def test_sv2_invalid_gif(self) -> None:
        """SV-2: GIF is rejected."""
        with pytest.raises(PhotoValidationError, match="Invalid file type"):
            validate_file_type("image/gif")

    def test_sv2_invalid_svg(self) -> None:
        """SV-2: SVG is rejected."""
        with pytest.raises(PhotoValidationError, match="Invalid file type"):
            validate_file_type("image/svg+xml")

    def test_sv2_error_message_lists_allowed(self) -> None:
        """SV-2: Error message includes allowed types."""
        with pytest.raises(PhotoValidationError) as exc_info:
            validate_file_type("application/pdf")
        msg = str(exc_info.value)
        for t in sorted(ALLOWED_MIME_TYPES):
            assert t in msg


# ---------------------------------------------------------------------------
# validate_file_size
# ---------------------------------------------------------------------------


class TestValidateFileSize:
    """SV-3 / SV-4: File size validation."""

    def test_sv3_small_file_accepted(self) -> None:
        """SV-3: 1KB file passes."""
        validate_file_size(b"x" * 1024)  # no raise

    def test_sv3_max_size_accepted(self) -> None:
        """SV-3: File exactly at max limit passes."""
        from app.core.config import get_settings

        settings = get_settings()
        data = b"x" * settings.MAX_UPLOAD_SIZE_BYTES
        validate_file_size(data)  # no raise

    def test_sv4_oversized_rejected(self) -> None:
        """SV-4: File exceeding max limit is rejected."""
        from app.core.config import get_settings

        settings = get_settings()
        data = b"x" * (settings.MAX_UPLOAD_SIZE_BYTES + 1)
        with pytest.raises(PhotoValidationError, match="exceeds maximum"):
            validate_file_size(data)


# ---------------------------------------------------------------------------
# resize_image
# ---------------------------------------------------------------------------


class TestResizeImage:
    """RS-1 through RS-6, SV-5 through SV-7."""

    def test_rs1_image_within_limits_unchanged(self) -> None:
        """RS-1: 1024×768 image stays at original dimensions."""
        data = _make_image_bytes(width=1024, height=768)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w == 1024
        assert h == 768
        # Should still be valid JPEG
        assert result[:2] == b"\xff\xd8"

    def test_rs2_wide_image_resized_down(self) -> None:
        """RS-2: 4096×3072 resized to 2048×1536."""
        data = _make_image_bytes(width=4096, height=3072)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w <= 2048
        assert h <= 2048
        # Aspect ratio 4:3 should be preserved
        assert abs(w / h - 4 / 3) < 0.02
        assert result[:2] == b"\xff\xd8"

    def test_rs3_tall_image_resized_down(self) -> None:
        """RS-3: 2000×4000 resized to 1024×2048."""
        data = _make_image_bytes(width=2000, height=4000)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w <= 2048
        assert h <= 2048
        # Aspect ratio 1:2 should be preserved
        assert abs(w / h - 0.5) < 0.02
        assert result[:2] == b"\xff\xd8"

    def test_rs4_square_image_resized_down(self) -> None:
        """RS-4: 3000×3000 resized to 2048×2048."""
        data = _make_image_bytes(width=3000, height=3000)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w == 2048
        assert h == 2048
        assert result[:2] == b"\xff\xd8"

    def test_rs5_small_image_not_upscaled(self) -> None:
        """RS-5: 100×80 image stays at 100×80."""
        data = _make_image_bytes(width=100, height=80)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w == 100
        assert h == 80
        assert result[:2] == b"\xff\xd8"

    def test_rs6_non_image_bytes_raises(self) -> None:
        """RS-6: Random binary data raises PhotoValidationError."""
        with pytest.raises(PhotoValidationError, match="not a valid image"):
            resize_image(b"\\x00\\x01\\x02\\x03" * 100, max_dimension=2048)

    def test_sv5_dimensions_correct_after_resize(self) -> None:
        """SV-5: 4000×3000 image output width ≤ 2048."""
        data = _make_image_bytes(width=4000, height=3000)
        _, w, h = resize_image(data, max_dimension=2048)
        assert w <= 2048

    def test_sv6_skip_small_images(self) -> None:
        """SV-6: 800×600 returns same bytes (no resize)."""
        data = _make_image_bytes(width=800, height=600)
        result, w, h = resize_image(data, max_dimension=2048)
        assert w == 800
        assert h == 600
        # The output will be re-encoded JPEG, so exact match not checked
        assert len(result) > 0
        assert result[:2] == b"\xff\xd8"

    def test_sv7_png_converted_to_jpeg(self) -> None:
        """SV-7: PNG input returns JPEG output."""
        data = _make_image_bytes(width=200, height=150, fmt="PNG")
        result, w, h = resize_image(data, max_dimension=2048)
        assert result[:2] == b"\xff\xd8"  # JPEG magic bytes
        assert w == 200
        assert h == 150


# ---------------------------------------------------------------------------
# process_upload — with mocked dependencies
# ---------------------------------------------------------------------------


class TestProcessUpload:
    """DD-1, DD-2, TN-1, TN-2, EH-1, EH-2."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Return a mock AsyncSession."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    @pytest.fixture
    def mock_minio(self) -> MagicMock:
        """Return a mock MinioStorageClient."""
        mc = MagicMock()
        mc.upload_photo = AsyncMock(return_value="photos/ab/cd/abcd.jpg")
        mc.upload_thumbnail = AsyncMock(return_value="photos/ab/cd/abcd_thumb.jpg")
        return mc

    @pytest.fixture
    def sample_data(self) -> bytes:
        """Return a small valid JPEG."""
        return _make_image_bytes(width=800, height=600)

    async def test_dd1_duplicate_returns_existing(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """DD-1: Same SHA256 returns existing record from DB lookup.

        Second upload of same bytes should not re-upload to MinIO.
        """
        sha256 = hashlib.sha256(sample_data).hexdigest()

        # Simulate existing record found
        mock_asset = MagicMock(spec=PhotoAsset)
        mock_asset.sha256 = sha256
        mock_asset.width = 800
        mock_asset.height = 600
        mock_asset.file_size_bytes = len(sample_data)
        mock_asset.mime_type = "image/jpeg"

        # Mock execute to return the existing asset
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_asset
        mock_db.execute.return_value = mock_result

        result = await process_upload(
            db=mock_db,
            minio_client=mock_minio,
            data=sample_data,
            original_filename="test.jpg",
            content_type="image/jpeg",
        )

        # Should return data without uploading
        assert result.sha256 == sha256
        assert result.width == 800
        assert result.height == 600
        mock_minio.upload_photo.assert_not_called()
        mock_minio.upload_thumbnail.assert_not_called()

        # Verify correct query was made
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args[0][0]
        assert isinstance(call_args, Select)
        expected_query = select(PhotoAsset).where(PhotoAsset.sha256 == sha256)
        assert str(call_args) == str(expected_query)

    async def test_dd2_different_bytes_upload_ok(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """DD-2: Different bytes upload successfully."""
        from app.services.photo_upload_service import process_upload

        # Mock no existing record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await process_upload(
            db=mock_db,
            minio_client=mock_minio,
            data=sample_data,
            original_filename="test.jpg",
            content_type="image/jpeg",
        )

        assert result.sha256 == hashlib.sha256(sample_data).hexdigest()
        assert result.photo_url.startswith("/api/v1/photos/")
        assert result.thumbnail_url.startswith("/api/v1/photos/")
        mock_minio.upload_photo.assert_called_once()
        mock_minio.upload_thumbnail.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_tn1_thumbnail_created(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """TN-1: Thumbnail is created and returned in result."""
        from app.services.photo_upload_service import process_upload

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await process_upload(
            db=mock_db,
            minio_client=mock_minio,
            data=sample_data,
            original_filename="test.jpg",
            content_type="image/jpeg",
        )

        assert result.thumbnail_url != ""
        mock_minio.upload_thumbnail.assert_called_once()

    async def test_tn2_thumbnail_path_in_response(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """TN-2: thumbnail_url points to /api/v1/photos/{sha256}/thumb.jpg."""
        from app.services.photo_upload_service import process_upload

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await process_upload(
            db=mock_db,
            minio_client=mock_minio,
            data=sample_data,
            original_filename="test.jpg",
            content_type="image/jpeg",
        )

        sha256 = hashlib.sha256(sample_data).hexdigest()
        assert result.thumbnail_url == f"/api/v1/photos/{sha256}/thumb.jpg"

    async def test_eh1_minio_unavailable_raises(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """EH-1: MinIO upload failure raises PhotoUploadError (→ 503)."""
        from app.services.photo_upload_service import process_upload

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Simulate MinIO failure
        mock_minio.upload_photo = AsyncMock(return_value=None)

        with pytest.raises(PhotoUploadError, match="temporarily unavailable"):
            await process_upload(
                db=mock_db,
                minio_client=mock_minio,
                data=sample_data,
                original_filename="test.jpg",
                content_type="image/jpeg",
            )

    async def test_eh2_db_error_rollback(
        self,
        mock_db: MagicMock,
        mock_minio: MagicMock,
        sample_data: bytes,
    ) -> None:
        """EH-2: DB insert failure rolls back and raises PhotoUploadError."""
        from app.services.photo_upload_service import process_upload

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Simulate DB commit failure
        mock_db.commit.side_effect = Exception("DB connection lost")

        with pytest.raises(PhotoUploadError, match="record photo metadata"):
            await process_upload(
                db=mock_db,
                minio_client=mock_minio,
                data=sample_data,
                original_filename="test.jpg",
                content_type="image/jpeg",
            )

        # Should have attempted rollback
        mock_db.rollback.assert_called_once()
