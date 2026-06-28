# Test Plan: STORY-31 — Auto Thumbnail Generation (IMG-3)

**ref:** STORY-31
**epic:** Epic 6 — Photo Storage (IMG-3)
**spec module:** `120-CACHING-STORAGE.md`

---

## 1. Test Scope

| Layer | Focus |
|-------|-------|
| Unit: storage | `MinioStorageClient` thumbnail upload method |
| Unit: pipeline | Thumbnail generation in `_process_photos()` |
| Integration: API | Thumbnail serving endpoint with cache headers |
| Regression | All existing tests continue to pass |

---

## 2. Test Cases

### 2.1 Unit — Thumbnail Generation & Upload

| ID | Test | Expected | Type |
|----|------|----------|------|
| TN-1 | Generate thumbnail from JPEG bytes via Pillow | Returns 400×300 JPEG bytes | unit |
| TN-2 | Thumbnail preserves aspect ratio then center-crops | Exact 400×300 dimensions | unit |
| TN-3 | Non-image bytes raise gracefully | Logged warning, thumbnail not uploaded | unit |
| TN-4 | Thumbnail uploaded to correct MinIO path | Object name ends with `_thumb.jpg` | unit |
| TN-5 | Thumbnail object path uses same SHA256 directory | `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg` | unit |

### 2.2 Unit — Pipeline Integration

| ID | Test | Expected | Type |
|----|------|----------|------|
| TN-10 | `_process_photos()` generates + uploads thumbnail after original | Both `path` and `thumbnail_path` in returned dict | unit |
| TN-11 | Thumbnail failure does not block original photo upload | Original stored, thumbnail_path is `null`/missing | unit |
| TN-12 | MinIO unavailable skips both original and thumbnail | Empty list returned | unit |
| TN-13 | Empty photo list skips thumbnail processing | Empty list returned promptly | unit |

### 2.3 Integration — Thumbnail Serving API

| ID | Test | Expected | Type |
|----|------|----------|------|
| TN-20 | `GET /api/v1/photos/{sha256}/thumb.jpg` returns 200 | Binary JPEG response | integration |
| TN-21 | Response includes `Cache-Control: public, max-age=31536000, immutable` | Header present | integration |
| TN-22 | Response includes `ETag: "{sha256}_thumb"` | Header matches pattern | integration |
| TN-23 | `If-None-Match` with matching ETag returns 304 | Not modified | integration |
| TN-24 | Non-existent SHA256 returns 404 | `{"detail": "Thumbnail not found"}` | integration |
| TN-25 | Invalid SHA256 format returns 422 | `{"detail": "Invalid SHA256 hash"}` | integration |

### 2.4 Regression

| ID | Test | Expected | Type |
|----|------|----------|------|
| TN-30 | Existing photo endpoint still serves originals | All STORY-29 tests pass | regression |
| TN-31 | All pipeline tests pass | scrapper-base test suite green | regression |
| TN-32 | All API tests pass | real-estate-api test suite green | regression |

---

## 3. Test Infrastructure

### 3.1 Scrapper-base tests
- Mock `MinioStorageClient` (existing fixture in `conftest.py`)
- Mock `httpx` responses for photo download
- Use real Pillow to generate test image bytes (100×80 or similar)

### 3.2 Real-estate-api tests
- Existing `app_with_minio` fixture from STORY-29
- Pre-upload a thumbnail to mock MinIO for 200/304 tests
- Verify 404 for missing thumbnails

---

## 4. Verification Commands

```bash
# Scrapper-base tests
cd src/scrapper-base && uv run -- pytest tests/ -v

# Real-estate-api tests
cd src/real-estate-api && uv run -- pytest tests/ -v

# Lint + types
cd src/scrapper-base && uv run -- ruff check src/ tests/
cd src/scrapper-base && uv run -- mypy src/

cd src/real-estate-api && uv run -- ruff check app/ tests/
cd src/real-estate-api && uv run -- mypy app/
```
