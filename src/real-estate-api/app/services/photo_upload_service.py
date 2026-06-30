"""
Photo upload orchestration service.

Provides validation (file type, file size), image resizing via Pillow,
and the full ``process_upload`` pipeline that stores photos in MinIO,
generates thumbnails, and records metadata in the database.
"""

import hashlib
import io
from dataclasses import dataclass

import structlog
from PIL import Image
from scraper_base.models import PhotoAsset
from scraper_base.storage import MinioStorageClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

# Build allowed set from config list for fast membership checks
ALLOWED_MIME_TYPES: set[str] = set(settings.ALLOWED_UPLOAD_MIME_TYPES)


class PhotoValidationError(ValueError):
    """Raised when uploaded photo fails validation (type, size, or content)."""


class PhotoUploadError(RuntimeError):
    """Raised when photo storage fails (MinIO or database issue)."""


@dataclass
class UploadResult:
    """Result of a successful photo upload."""

    sha256: str
    photo_url: str
    thumbnail_url: str
    width: int
    height: int
    file_size_bytes: int
    mime_type: str


def validate_file_type(content_type: str) -> None:
    """Validate the MIME type is an allowed image format.

    Args:
        content_type: The ``Content-Type`` header value from the upload.

    Raises:
        PhotoValidationError: If the MIME type is not in the allowed set.

    """
    if content_type not in ALLOWED_MIME_TYPES:
        allowed_str = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise PhotoValidationError(
            f"Invalid file type '{content_type}'. Allowed: {allowed_str}",
        )


def validate_file_size(data: bytes) -> None:
    """Validate the file size does not exceed the configured maximum.

    Args:
        data: Raw file bytes.

    Raises:
        PhotoValidationError: If the data length exceeds
            ``MAX_UPLOAD_SIZE_BYTES``.

    """
    if len(data) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise PhotoValidationError(
            f"File size {len(data)} bytes exceeds maximum "
            f"{settings.MAX_UPLOAD_SIZE_BYTES} bytes",
        )


def resize_image(data: bytes, max_dimension: int = 2048) -> tuple[bytes, int, int]:
    """Resize image to fit within ``max_dimension`` while preserving aspect ratio.

    All images are converted to JPEG for consistency with the existing photo
    storage pipeline. If the image is already within limits, it is still
    converted to JPEG (no-op resize).

    Args:
        data: Raw image bytes (JPEG, PNG, or WebP).
        max_dimension: Maximum allowed pixel length on the longest side.

    Returns:
        A tuple of ``(resized_image_bytes, width, height)``.

    Raises:
        PhotoValidationError: If the image data cannot be opened by Pillow.

    """
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")  # type: ignore[assignment]  # PIL stubs: open() -> ImageFile, convert() -> Image
    except Exception as exc:
        raise PhotoValidationError(
            "Uploaded file is not a valid image or could not be processed",
        ) from exc

    original_width, original_height = img.size

    if original_width <= max_dimension and original_height <= max_dimension:
        # No resize needed — still convert to JPEG for consistency
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), original_width, original_height

    # Resize preserving aspect ratio
    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    new_width, new_height = img.size

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), new_width, new_height


async def process_upload(
    db: AsyncSession,
    minio_client: MinioStorageClient,
    data: bytes,
    original_filename: str | None,
    content_type: str,
    bucket: str = "property-photos",
) -> UploadResult:
    """Validate, resize, store, and return upload result.

    Full pipeline:
    1. Validate file type and size
    2. Compute SHA256 hash
    3. Check for existing record in ``photo_assets`` (dedup)
    4. Resize if needed (preserves aspect ratio, converts to JPEG)
    5. Upload full-size photo to MinIO
    6. Generate + upload 400×300 thumbnail to MinIO
    7. Insert ``PhotoAsset`` metadata row in database
    8. Return ``UploadResult``

    Args:
        db: An active async database session.
        minio_client: A ``MinioStorageClient`` instance for MinIO operations.
        data: Raw file bytes.
        original_filename: Original filename from the upload form.
        content_type: MIME type from the upload.
        bucket: MinIO bucket name.

    Returns:
        An ``UploadResult`` with SHA256, URLs, and dimensions.

    Raises:
        PhotoValidationError: If validation fails.
        PhotoUploadError: If MinIO or database storage fails.

    """
    # Step 1: Validation
    validate_file_type(content_type)
    validate_file_size(data)

    # Step 2: SHA256
    sha256 = hashlib.sha256(data).hexdigest()

    # Step 3: Dedup check — return existing record if found
    existing = await db.execute(
        select(PhotoAsset).where(PhotoAsset.sha256 == sha256),
    )
    existing_asset = existing.scalar_one_or_none()
    if existing_asset is not None:
        logger.info("Photo already exists, returning existing record", sha256=sha256)
        return UploadResult(
            sha256=existing_asset.sha256,
            photo_url=f"/api/v1/photos/{sha256}.jpg",
            thumbnail_url=f"/api/v1/photos/{sha256}/thumb.jpg",
            width=existing_asset.width,
            height=existing_asset.height,
            file_size_bytes=existing_asset.file_size_bytes,
            mime_type=existing_asset.mime_type,
        )

    # Step 4: Resize (convert to JPEG, possibly downscale)
    resized_data, width, height = resize_image(data, settings.MAX_UPLOAD_DIMENSION)

    # Step 5: Upload full-size photo to MinIO
    object_name = f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"
    try:
        uploaded_name = await minio_client.upload_photo(
            resized_data,
            object_name=object_name,
            content_type="image/jpeg",
        )
    except Exception as exc:
        logger.error("MinIO upload failed", sha256=sha256, error=str(exc))
        raise PhotoUploadError("Photo storage temporarily unavailable") from exc

    if uploaded_name is None:
        raise PhotoUploadError("Photo storage temporarily unavailable")

    # Step 6: Generate + upload thumbnail
    try:
        thumbnail_name = await minio_client.upload_thumbnail(resized_data)
    except Exception as exc:
        logger.warning("Thumbnail generation failed, continuing", sha256=sha256, error=str(exc))
        thumbnail_name = None

    # Step 7: Store metadata in DB
    asset = PhotoAsset(
        sha256=sha256,
        original_filename=original_filename,
        mime_type="image/jpeg",
        width=width,
        height=height,
        file_size_bytes=len(resized_data),
    )
    db.add(asset)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("DB insert failed for photo asset", sha256=sha256, error=str(exc))
        raise PhotoUploadError("Failed to record photo metadata") from exc

    # Step 8: Return result
    return UploadResult(
        sha256=sha256,
        photo_url=f"/api/v1/photos/{sha256}.jpg",
        thumbnail_url=f"/api/v1/photos/{sha256}/thumb.jpg" if thumbnail_name else "",
        width=width,
        height=height,
        file_size_bytes=len(resized_data),
        mime_type="image/jpeg",
    )
