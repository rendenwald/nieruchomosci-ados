# Implementation Plan: STORY-31 — Auto Thumbnail Generation (IMG-3)

**ref:** STORY-31
**epic:** Epic 6 — Photo Storage (IMG-3)

---

## Files to Modify

### 1. `src/scrapper-base/pyproject.toml`

Add `Pillow` dependency:

```toml
dependencies = [
    ...
    "Pillow>=10.0,<12.0",
]
```

### 2. `src/scrapper-base/src/scraper_base/storage.py`

Add `upload_thumbnail()` method to `MinioStorageClient`:

```python
from PIL import Image

async def upload_thumbnail(
    self,
    data: bytes,
    object_name: str | None = None,
    size: tuple[int, int] = (400, 300),
    quality: int = 85,
) -> str | None:
    """Generate and upload a thumbnail to MinIO.

    Args:
        data: Original photo bytes.
        object_name: Target object name. If None, derived from original SHA256.
        size: Desired thumbnail dimensions (width, height).
        quality: JPEG quality (1-100).

    Returns:
        Object name on success, None on failure.

    """
    if not self._available and self._initialised:
        logger.warning("MinIO unavailable, skipping thumbnail upload")
        return None

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")  # Ensure RGB mode for JPEG output
        img.thumbnail(size, Image.LANCZOS)

        # Center-crop to exact dimensions
        if img.size != size:
            left = (img.width - size[0]) / 2
            top = (img.height - size[1]) / 2
            right = left + size[0]
            bottom = top + size[1]
            img = img.crop((left, top, right, bottom))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        thumb_bytes = buf.getvalue()
    except Exception as exc:
        logger.warning("Thumbnail generation failed", error=str(exc))
        return None

    # Derive thumbnail object name from original if not provided
    if object_name is None:
        sha256 = hashlib.sha256(data).hexdigest()
        object_name = f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg"

    return await self.upload_photo(thumb_bytes, object_name=object_name, content_type="image/jpeg")
```

### 3. `src/scrapper-base/src/scraper_base/pipeline.py`

Modify `_process_photos()` — after uploading each photo, generate and upload thumbnail:

**Current (STORY-28):**
```python
object_name = await self._minio.upload_photo(response.content)
if object_name:
    results.append({
        "path": object_name,
        "url": url,
        "order": len(results) + 1,
    })
```

**New:**
```python
object_name = await self._minio.upload_photo(response.content)
if object_name:
    # Generate and upload thumbnail
    thumbnail_name = await self._minio.upload_thumbnail(response.content)
    photo_entry = {
        "path": object_name,
        "url": url,
        "order": len(results) + 1,
    }
    if thumbnail_name:
        photo_entry["thumbnail_path"] = thumbnail_name
    results.append(photo_entry)
```

### 4. `src/real-estate-api/app/routers/photos.py`

Add thumbnail endpoint:

```python
@router.get("/{sha256}/thumb.jpg")
async def get_thumbnail(sha256: str, request: Request) -> Response:
    """Serve a photo thumbnail from MinIO with CDN-friendly cache headers."""
    normalized = _validate_sha256(sha256)
    if not normalized:
        return Response(
            status_code=422,
            content='{"detail": "Invalid SHA256 hash"}',
            media_type="application/json",
        )

    # Thumbnail path convention
    object_path = f"photos/{normalized[:2]}/{normalized[2:4]}/{normalized}_thumb.jpg"
    etag_value = f'"{normalized}_thumb"'

    # ETag check
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag_value:
        return Response(
            status_code=304,
            headers={
                "ETag": etag_value,
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    client = _get_minio_client(request)
    if client is None:
        return Response(
            status_code=404,
            content='{"detail": "Thumbnail not found"}',
            media_type="application/json",
        )

    bucket = getattr(request.app.state, "minio_bucket", "property-photos")
    try:
        response = await asyncio.to_thread(
            client.get_object, bucket_name=bucket, object_name=object_path,
        )
        data = response.read()
        content_length = len(data)
        response.close()
        response.release_conn()
    except (S3Error, MinioException) as exc:
        logger.debug("Thumbnail not found", sha256=normalized, error=str(exc))
        return Response(
            status_code=404,
            content='{"detail": "Thumbnail not found"}',
            media_type="application/json",
        )

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag_value,
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
        },
    )
```

---

## Files to Add

### 5. `src/scrapper-base/tests/test_thumbnail_processor.py`

Test thumbnail generation in the pipeline:

```python
"""Tests for thumbnail generation in the photo processing pipeline."""

import hashlib
from unittest.mock import AsyncMock

import pytest
from PIL import Image

# TN-1: Generate thumbnail from JPEG bytes
# TN-2: Thumbnail dimensions are 400x300
# TN-4: Thumbnail uploaded with _thumb path convention
# TN-11: Thumbnail failure does not block original upload
```

### 6. Additions to `src/real-estate-api/tests/test_photos.py`

Add tests for the thumbnail endpoint:

```python
# TN-20: GET /api/v1/photos/{sha256}/thumb.jpg returns 200
# TN-21: Cache-Control header present
# TN-24: 404 for non-existent thumbnail
# TN-25: 422 for invalid SHA256
```

---

## Execution Order

| Step | Action | File(s) | Status |
|------|--------|---------|--------|
| 1 | Add Pillow dependency | `scrapper-base/pyproject.toml` | ✅ Done |
| 2 | Add `upload_thumbnail()` method | `scrapper-base/src/scraper_base/storage.py` | ✅ Done |
| 3 | Modify `_process_photos()` for thumbnails | `scrapper-base/src/scraper_base/pipeline.py` | ✅ Done |
| 4 | Add thumbnail serving endpoint | `real-estate-api/app/routers/photos.py` | ✅ Done |
| 5 | Add scrapper-base tests | `scrapper-base/tests/test_thumbnail_processor.py` | ✅ Done |
| 6 | Add API tests | `real-estate-api/tests/test_photos.py` | ✅ Done |
| 7 | Run full test suite + lint + mypy | Both packages | ✅ Done |

---

## Verification

```bash
cd src/scrapper-base && uv run -- pytest tests/ -v && uv run -- ruff check src/ tests/ && uv run -- mypy src/
cd src/real-estate-api && uv run -- pytest tests/ -v && uv run -- ruff check app/ tests/ && uv run -- mypy app/
```

---

## Execution Log

| Date | Action | Outcome |
|------|--------|---------|
| 2026-06-28 | Step 1: Added Pillow>=10.0,<12.0 to scrapper-base/pyproject.toml | Done |
| 2026-06-28 | Step 2: Added upload_thumbnail() to MinioStorageClient | Done |
| 2026-06-28 | Step 3: Modified _process_photos() to generate thumbnails | Done |
| 2026-06-28 | Step 4: Added GET /{sha256}/thumb.jpg endpoint to photos router | Done |
| 2026-06-28 | Step 5: Created test_thumbnail_processor.py (TN-1 through TN-13 + regression) | Done |
| 2026-06-28 | Step 6: Added thumbnail endpoint tests (TN-20 through TN-25) | Done |
| 2026-06-28 | Step 7: ruff check ✅ / mypy ✅ / pytest (109+85=194) ✅ | All passing |
