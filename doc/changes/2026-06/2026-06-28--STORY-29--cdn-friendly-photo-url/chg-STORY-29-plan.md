# Implementation Plan: STORY-29 — CDN-Friendly Photo URL (IMG-2)

**ref:** STORY-29
**status:** draft

---

## Phase 1: Photo serving endpoint

### Task 1.1: Create `src/real-estate-api/app/routers/photos.py`

New FastAPI router with a single endpoint `GET /photos/{sha256}.jpg`:

```python
@router.get("/{sha256}.jpg")
async def get_photo(sha256: str, request: Request) -> Response:
    """Serve a photo from MinIO with CDN-friendly cache headers."""
```

**Key implementation details:**
- Validate `sha256` is a 64-char hex string (return 422 if not)
- Construct MinIO path: `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg`
- Check `If-None-Match` header — return 304 if ETag matches
- Fetch object from MinIO using `get_object()` (not presigned URL)
- Return `StreamingResponse` with the object content
- Set headers: `Content-Type`, `Content-Length`, `Cache-Control`, `ETag`, `Accept-Ranges`
- On `MinioException` → return 404
- Use `MinioStorageClient` from scrapper-base (instantiate with env vars)

### Task 1.2: Register router in `src/real-estate-api/app/main.py`

Add `from app.routers import photos` and:
```python
app.include_router(photos.router, prefix="/api/v1/photos")
```

### Task 1.3: Update `property_to_card` to use new photo URLs

Modify `src/real-estate-api/app/services/property_service.py`:
- Instead of returning the raw photo path from storage, construct the API URL
- Pattern: `/api/v1/photos/{sha256}.jpg`

---

## Phase 2: Tests

### Task 2.1: Add MinIO fixtures to test conftest

Mock MinIO responses for photo serving tests.

### Task 2.2: Create test file

`src/real-estate-api/tests/test_photos.py` covering:
- 200 response with valid sha256
- 304 when ETag matches
- 422 for invalid sha256 format
- 404 when photo doesn't exist
- Cache-Control header present
- Content-Type is image/jpeg

---

## Phase 3: Verify

```bash
cd src/real-estate-api
ruff check app/ tests/
mypy app/
pytest tests/test_photos.py -v
```
