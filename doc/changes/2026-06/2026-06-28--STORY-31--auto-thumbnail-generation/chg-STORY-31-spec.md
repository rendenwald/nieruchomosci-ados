# Specification: STORY-31 — Auto Thumbnail Generation (IMG-3)

**ref:** STORY-31
**epic:** Epic 6 — Photo Storage (IMG-3)
**spec module:** `120-CACHING-STORAGE.md`
**status:** draft

---

## 1. Problem

When photos are stored in MinIO via `_process_photos()`, only the original
full-resolution photo is saved. The UI needs a 400×300 thumbnail for listing
cards, property grid views, and map markers. Currently every consumer would
need to download full-resolution images, wasting bandwidth and slowing page
loads. Thumbnails must be generated automatically at store time.

---

## 2. Goals

1. Generate 400×300 thumbnail automatically when each photo is stored in MinIO
2. Store thumbnail at a predictable path alongside the original
3. Serve thumbnails via CDN-friendly `GET /api/v1/photos/{sha256}/thumb.jpg`
4. Graceful degradation — thumbnail failure does not block photo storage

---

## 3. Acceptance Criteria

| ID | Criteria |
|----|----------|
| AC-1 | `_process_photos()` generates a 400×300 thumbnail via Pillow **after** uploading the original photo to MinIO |
| AC-2 | Thumbnail is stored at `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg` in the same MinIO bucket |
| AC-3 | `GET /api/v1/photos/{sha256}/thumb.jpg` returns the thumbnail with `Cache-Control: public, max-age=31536000, immutable` + `ETag` |
| AC-4 | 404 returned when thumbnail does not exist in MinIO |
| AC-5 | Thumbnail generation failure logs a warning but does not fail the pipeline — original photo is still stored |
| AC-6 | Photo metadata dict includes `thumbnail_path` field alongside `path` |
| AC-7 | `MAX_PHOTOS_PER_PROPERTY` cap applies — at most 20 thumbnails generated (1:1 with originals) |
| AC-8 | All existing tests pass (`pytest`, `ruff`, `mypy`) |

---

## 4. Non-Goals

- No frontend changes (SvelteKit)
- No photo upload endpoint (STORY-30)
- No user-uploaded photo thumbnails
- No CDN configuration
- No thumbnail regeneration for existing photos

---

## 5. Scope

### 5.1 Files to Modify — scrapper-base

| File | Change |
|------|--------|
| `pyproject.toml` | Add `Pillow>=10.0,<12.0` dependency |
| `src/scraper_base/storage.py` | Add `upload_thumbnail()` method to `MinioStorageClient` |
| `src/scraper_base/pipeline.py` | Modify `_process_photos()` to call thumbnail generation after each photo upload |

### 5.2 Files to Modify — real-estate-api

| File | Change |
|------|--------|
| `app/routers/photos.py` | Add `GET /{sha256}/thumb.jpg` endpoint that serves thumbnails from MinIO |

### 5.3 Files to Add — tests

| File | Purpose |
|------|---------|
| `tests/test_thumbnail_processor.py` | Test thumbnail generation in pipeline |
| Additions to `routers/test_photos.py` | Test thumbnail serving endpoint |

---

## 6. Thumbnail Processing

### Algorithm

1. After `upload_photo()` returns the object name for the original photo:
   a. Open the raw bytes with Pillow
   b. Use `Image.thumbnail((400, 300))` to resize while preserving aspect ratio (fits within box)
   c. If the result is not exactly 400×300, center-crop to hit exact dimensions
   d. Save as JPEG with quality 85
2. Upload the thumbnail via `upload_photo()` with explicit object name
   `photos/{sha256[:2]}/{sha256[2:4]}/{sha256}_thumb.jpg`
3. Wrap in try/except — failure logs warning, photo storage continues

### Flow

```
_process_photos() pipeline:
  for each photo URL:
    1. Download via httpx
    2. Upload original → SHA256 dedup → MinIO
    3. Generate 400×300 thumbnail via Pillow
    4. Upload thumbnail to MinIO with _thumb suffix
    5. Store both paths in photo metadata dict
```

### Photo metadata shape (updated)

```json
{
  "path": "photos/ab/cd/abcdef...123.jpg",
  "thumbnail_path": "photos/ab/cd/abcdef...123_thumb.jpg",
  "url": "https://original-source.com/photo.jpg",
  "order": 1
}
```

---

## 7. API Design

### Thumbnail endpoint

```
GET /api/v1/photos/{sha256}/thumb.jpg
```

Path parameters:
- `sha256` — SHA-256 hex digest of the **original** photo (64 hex chars)

Response (200):
```http
HTTP/1.1 200 OK
Content-Type: image/jpeg
Content-Length: ...
Cache-Control: public, max-age=31536000, immutable
ETag: "{sha256}_thumb"
Accept-Ranges: bytes

<binary thumbnail data>
```

Response (404):
```json
{
  "detail": "Thumbnail not found"
}
```

Implementation: construct the MinIO path from the SHA256, fetch the `_thumb.jpg` variant, and return with the same caching headers as the photo endpoint.

---

## 8. Dependencies

- MinIO must be running and accessible
- Pillow must be installed (new dependency on scrapper-base)
- `upload_photo()` must already have succeeded before thumbnail generation

---

## 9. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Thumbnail naming | `{sha256}_thumb.jpg` | Predictable from original SHA256; no extra DB metadata needed |
| Endpoint pattern | `/photos/{sha256}/thumb.jpg` | Clean REST; separate from original photo route |
| Image library | Pillow `thumbnail()` + center-crop | Standard Python library; `thumbnail()` preserves aspect ratio |
| Thumbnail quality | JPEG quality 85 | Good balance of file size vs visual quality |
| Failure handling | Log warning, continue | Photo storage should not depend on thumbnail success |

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| PIL large dependency | Added only to scrapper-base (not real-estate-api); ~10MB acceptable |
| Thumbnail generation slows pipeline | Async within existing httpx loop; failure is non-blocking |
| `_thumb` suffix convention | Documented and consistent; frontend derives thumbnail URL from photo SHA256 |
