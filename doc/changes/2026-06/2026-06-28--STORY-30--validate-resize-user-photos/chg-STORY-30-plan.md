# Implementation Plan: STORY-30 — Validate, Resize and Store User-Uploaded Photos

**ref:** STORY-30
**epic:** Epic 6 — Photo Storage

---

## Files to Modify / Create

### Phase 1: Infrastructure

#### 1. `src/real-estate-api/app/core/config.py`
Add upload validation env vars:
```python
# Photo upload limits
MAX_UPLOAD_SIZE_BYTES: int = 10_485_760        # 10 MB
MAX_UPLOAD_DIMENSION: int = 2048                # max pixels on longest side
ALLOWED_UPLOAD_MIME_TYPES: list[str] = [
    "image/jpeg",
    "image/png",
    "image/webp",
]
```

#### 2. Alembic migration — `photo_assets` table
Create migration:
```python
"""create photo_assets table

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"  # depends on existing migration

def upgrade():
    op.create_table(
        "photo_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_photo_assets_sha256", "photo_assets", ["sha256"])

def downgrade():
    op.drop_index("ix_photo_assets_sha256")
    op.drop_table("photo_assets")
```

#### 3. `src/real-estate-api/app/models/photo_asset.py`
```python
"""PhotoAsset ORM model for tracking uploaded photo metadata."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PhotoAsset(Base):
    __tablename__ = "photo_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

#### 4. `src/real-estate-api/app/database.py`
Ensure `app.models.photo_asset` is imported for Alembic auto-detection.

---

### Phase 2: Service Layer

#### 5. `src/real-estate-api/app/services/photo_upload_service.py`
```python
"""Photo upload orchestration service."""

import hashlib
import io
from dataclasses import dataclass

import structlog
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.photo_asset import PhotoAsset

logger = structlog.get_logger(__name__)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class PhotoValidationError(ValueError):
    """Raised when uploaded photo fails validation."""


class PhotoUploadError(RuntimeError):
    """Raised when photo storage fails (MinIO/DB issue)."""


@dataclass
class UploadResult:
    sha256: str
    photo_url: str
    thumbnail_url: str
    width: int
    height: int
    file_size_bytes: int
    mime_type: str


def validate_file_type(content_type: str) -> None:
    """Validate the MIME type is an allowed image format."""
    if content_type not in ALLOWED_MIME_TYPES:
        raise PhotoValidationError(
            f"Invalid file type '{content_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


def validate_file_size(data: bytes) -> None:
    """Validate file size does not exceed the configured limit."""
    if len(data) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise PhotoValidationError(
            f"File size {len(data)} bytes exceeds maximum "
            f"{settings.MAX_UPLOAD_SIZE_BYTES} bytes"
        )


def resize_image(data: bytes, max_dimension: int = 2048) -> tuple[bytes, int, int]:
    """Resize image to fit within max_dimension while preserving aspect ratio.

    Returns:
        Tuple of (resized_image_bytes, width, height).
        If image is already within limits, returns original bytes.
    """
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")

    original_width, original_height = img.size

    if original_width <= max_dimension and original_height <= max_dimension:
        # No resize needed — still convert to JPEG for consistency
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), original_width, original_height

    # Resize preserving aspect ratio
    img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    new_width, new_height = img.size

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), new_width, new_height


async def process_upload(
    db: AsyncSession,
    minio_client,
    data: bytes,
    original_filename: str | None,
    content_type: str,
    bucket: str = "property-photos",
) -> UploadResult:
    """Validate, resize, store, and return upload result.

    Steps:
    1. Validate file type and size
    2. Compute SHA256
    3. Check for existing record (dedup)
    4. Resize if needed
    5. Upload to MinIO
    6. Generate thumbnail
    7. Store metadata in DB
    """
    # Step 1: Validation
    validate_file_type(content_type)
    validate_file_size(data)

    # Step 2: SHA256
    sha256 = hashlib.sha256(data).hexdigest()

    # Step 3: Dedup check
    existing = await db.execute(
        select(PhotoAsset).where(PhotoAsset.sha256 == sha256)
    )
    existing_asset = existing.scalar_one_or_none()
    if existing_asset:
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

    # Step 4: Resize
    resized_data, width, height = resize_image(data, settings.MAX_UPLOAD_DIMENSION)

    # Step 5: Upload to MinIO
    object_name = f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"
    try:
        uploaded_name = await minio_client.upload_photo(
            resized_data, object_name=object_name, content_type="image/jpeg"
        )
    except Exception as exc:
        logger.error("MinIO upload failed", sha256=sha256, error=str(exc))
        raise PhotoUploadError("Photo storage temporarily unavailable") from exc

    if uploaded_name is None:
        raise PhotoUploadError("Photo storage temporarily unavailable")

    # Step 6: Generate thumbnail
    try:
        thumbnail_name = await minio_client.upload_thumbnail(resized_data)
    except Exception:
        logger.warning("Thumbnail generation failed, continuing", sha256=sha256)
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

    return UploadResult(
        sha256=sha256,
        photo_url=f"/api/v1/photos/{sha256}.jpg",
        thumbnail_url=f"/api/v1/photos/{sha256}/thumb.jpg"
        if thumbnail_name
        else "",
        width=width,
        height=height,
        file_size_bytes=len(resized_data),
        mime_type="image/jpeg",
    )
```

---

### Phase 3: API Endpoint

#### 6. `src/real-estate-api/app/routers/photos.py`
Add upload endpoint:
```python
import io
from fastapi import Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.photo_upload_service import (
    PhotoValidationError,
    PhotoUploadError,
    process_upload,
)

@router.post("/upload", status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Upload a photo. Validates, resizes, stores in MinIO, records metadata.

    Returns SHA256 hash, photo URL, and thumbnail URL.
    """
    client = _get_minio_client(request)
    if client is None:
        raise HTTPException(status_code=503, detail="Photo storage temporarily unavailable")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        result = await process_upload(
            db=db,
            minio_client=client,
            data=data,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            bucket=getattr(request.app.state, "minio_bucket", "property-photos"),
        )
    except PhotoValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PhotoUploadError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "sha256": result.sha256,
        "photo_url": result.photo_url,
        "thumbnail_url": result.thumbnail_url,
        "width": result.width,
        "height": result.height,
        "file_size_bytes": result.file_size_bytes,
        "mime_type": result.mime_type,
    }
```

---

### Phase 4: Tests

#### 7. `src/real-estate-api/tests/test_photo_upload_service.py`
Test validation, resize, and process_upload flow.

#### 8. `src/real-estate-api/tests/test_photo_upload.py`
Test upload endpoint with mocked MinIO + in-memory SQLite.

---

## Execution Order

| Step | Action | File(s) |
|------|--------|---------|
| 1 | Add config env vars | `app/core/config.py` |
| 2 | Create Alembic migration | Alembic versions dir |
| 3 | Create PhotoAsset model | `app/models/photo_asset.py` |
| 4 | Update database imports | `app/database.py` |
| 5 | Create photo_upload_service | `app/services/photo_upload_service.py` |
| 6 | Add upload endpoint | `app/routers/photos.py` |
| 7 | Add service tests | `tests/test_photo_upload_service.py` |
| 8 | Add endpoint tests | `tests/test_photo_upload.py` |
| 9 | Run full suite + lint + mypy | Both projects |

---

## Verification

```bash
cd src/real-estate-api && uv run -- pytest tests/ -v && uv run -- ruff check app/ tests/ && uv run -- mypy app/
cd src/scrapper-base && uv run -- pytest tests/ -v && uv run -- ruff check src/ tests/ && uv run -- mypy src/
```
