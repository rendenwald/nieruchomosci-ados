# Specification: STORY-30 — Validate, Resize and Store User-Uploaded Photos (IMG-2)

**ref:** STORY-30
**epic:** Epic 6 — Photo Storage (IMG-2)
**spec module:** `120-CACHING-STORAGE.md`, `070-DATABASE.md`, `080-API.md`
**status:** draft

---

## 1. Problem

The platform can store scraped photos in MinIO (STORY-28, STORY-29, STORY-31)
but has no mechanism for users to upload their own photos. User-uploaded photos
(profile avatars, property photos from user-submitted listings, etc.) need
validation, resizing, and secure storage with SHA256 deduplication.

---

## 2. Goals

1. Provide `POST /api/v1/photos/upload` endpoint accepting multipart file uploads
2. Validate file type (JPEG/PNG/WebP), size (max 10MB), and dimensions (max 2048px)
3. Resize oversized images down to max 2048px on longest side (maintain aspect ratio)
4. Store with SHA256 deduplication in MinIO (reuse existing path convention)
5. Auto-generate 400×300 thumbnail (reuse `upload_thumbnail()` from STORY-31)
6. Track photo metadata in a `photo_assets` database table
7. Return SHA256 hash, photo URL, and thumbnail URL in the response

---

## 3. Acceptance Criteria

| ID | Criteria |
|----|----------|
| AC-1 | `POST /api/v1/photos/upload` accepts JPEG/PNG/WebP files via multipart form and returns 201 |
| AC-2 | Invalid file type (e.g., GIF, SVG, PDF) returns 422 with descriptive error message |
| AC-3 | Files > 10MB return 422 with descriptive error message |
| AC-4 | Images > 2048px on any side are resized down (aspect ratio preserved) |
| AC-5 | Photo is stored in MinIO at `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg` (JPEG output regardless of input) |
| AC-6 | 400×300 thumbnail is stored at `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg` |
| AC-7 | Metadata recorded in `photo_assets` table: sha256, original_filename, mime_type, width, height, file_size_bytes, created_at |
| AC-8 | Response body includes: `sha256`, `photo_url`, `thumbnail_url` |
| AC-9 | Same SHA256 upload returns existing photo data (dedup — does not re-upload) |
| AC-10 | MinIO unavailable returns 503 with graceful error message |
| AC-11 | All existing tests pass (pytest, ruff, mypy) |

---

## 4. Non-Goals

- No auth enforcement (auth system not built yet; add `TODO` comment)
- No photo deletion endpoints (STORY-32)
- No gallery ordering or album features
- No client-side image manipulation
- No EXIF stripping (Pillow `thumbnail()` + save as JPEG effectively strips EXIF)

---

## 5. Scope

### 5.1 Files to Modify — scrapper-base

| File | Change |
|------|--------|
| `src/scraper_base/storage.py` | Add `resize_image()` helper function (Pillow) |
| `src/scraper_base/__init__.py` | Export `resize_image()` |

### 5.2 Files to Modify — real-estate-api

| File | Change |
|------|--------|
| `app/models/` | Add `PhotoAsset` SQLAlchemy model |
| `app/database.py` | Ensure models are imported for Alembic detection |
| `app/routers/photos.py` | Add `POST /upload` endpoint |
| `app/services/photo_upload_service.py` | New file — upload orchestration logic |
| `app/core/config.py` | Add upload validation env vars |
| Alembic migration | Create `photo_assets` table |

### 5.3 Files to Add — tests

| File | Purpose |
|------|---------|
| `tests/test_photo_upload.py` | Upload endpoint + validation tests |
| `tests/test_photo_upload_service.py` | Service layer unit tests |

---

## 6. API Design

### Upload endpoint

```
POST /api/v1/photos/upload
Content-Type: multipart/form-data

Body:
  file: <binary> (required)
```

Response (201):
```json
{
  "sha256": "abc123...",
  "photo_url": "/api/v1/photos/abc123....jpg",
  "thumbnail_url": "/api/v1/photos/abc123.../thumb.jpg",
  "width": 2048,
  "height": 1536,
  "file_size_bytes": 524288,
  "mime_type": "image/jpeg"
}
```

Response (422 — validation error):
```json
{
  "detail": "Invalid file type. Allowed: image/jpeg, image/png, image/webp"
}
```

Response (503 — MinIO unavailable):
```json
{
  "detail": "Photo storage temporarily unavailable"
}
```

---

## 7. Upload Flow

```
POST /api/v1/photos/upload
  │
  ├─ 1. Validate file type (content_type in allowed set)
  ├─ 2. Validate file size (< MAX_UPLOAD_SIZE_BYTES)
  ├─ 3. Read bytes, compute SHA256
  ├─ 4. Check photo_assets table for existing SHA256 → dedup
  │     └─ If found: return 200 with existing data
  ├─ 5. Open with Pillow, validate dimensions
  ├─ 6. If width > 2048 or height > 2048: resize down (aspect ratio)
  ├─ 7. Upload to MinIO via MinioStorageClient.upload_photo()
  ├─ 8. Generate + upload thumbnail via MinioStorageClient.upload_thumbnail()
  ├─ 9. Insert metadata row into photo_assets
  └─ 10. Return 201 response
```

---

## 8. Dependencies

- `Pillow` already available (added in STORY-31)
- `MinioStorageClient` from scrapper-base (already imported in real-estate-api)
- MinIO must be running and accessible
- PostgreSQL with `photo_assets` table created via Alembic

---

## 9. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Upload format | JPEG output always | Consistent with scraped photos; simpler frontend display |
| Max dimension | 2048px longest side | Sufficient for listing display; storage efficient |
| Max file size | 10MB | Generous for high-res photos; prevents abuse |
| Dedup strategy | SHA256 check before upload | Reuses same dedup pattern as scraped photos |
| Resize method | Pillow `thumbnail()` + center-crop | Consistent with STORY-31 thumbnail approach |
| DB table | `photo_assets` | Dedicated table; not coupled to property model |

---

## 10. Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `MAX_UPLOAD_SIZE_BYTES` | `10485760` (10MB) | Max upload file size |
| `MAX_UPLOAD_DIMENSION` | `2048` | Max pixel dimension on longest side |

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Large uploads consume memory | Read into memory (required for SHA256); max 10MB is manageable |
| Concurrent duplicate uploads | DB unique constraint on sha256; second insert fails → return existing |
| MinIO unavailable during upload | Catch exception, return 503, log warning |
| Image with embedded EXIF orientation | Pillow `thumbnail()` strips EXIF on JPEG save |
