# Test Plan: STORY-30 — Validate, Resize and Store User-Uploaded Photos

**ref:** STORY-30
**epic:** Epic 6 — Photo Storage

---

## 1. Test Strategy

- Unit tests for validation logic and image resize helper
- Integration tests for upload endpoint with mocked MinIO
- Service layer tests for upload orchestration
- No real MinIO — mock `MinioStorageClient`

---

## 2. Test Cases

### 2.1 Upload Endpoint — `POST /api/v1/photos/upload`

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| UP-1 | Upload valid JPEG returns 201 | POST with `image/jpeg` file | 201, body has sha256, photo_url, thumbnail_url |
| UP-2 | Upload valid PNG returns 201 | POST with `image/png` file | 201, body has all fields |
| UP-3 | Upload valid WebP returns 201 | POST with `image/webp` file | 201, body has all fields |
| UP-4 | Invalid file type returns 422 | POST with `application/pdf` file | 422, descriptive error message |
| UP-5 | Invalid file type (GIF) returns 422 | POST with `image/gif` | 422, descriptive error |
| UP-6 | File over size limit returns 422 | POST with file > MAX_UPLOAD_SIZE_BYTES | 422, descriptive error |
| UP-7 | Missing file returns 422 | POST without file part | 422 |
| UP-8 | Empty file returns 422 | POST with empty bytes | 422 or 500 — document behavior |

### 2.2 Image Resize

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| RS-1 | Image within limits unchanged | Upload 1024×768 JPEG | Saved at original dimensions |
| RS-2 | Image too wide resized down | Upload 4096×3072 JPEG | Saved at 2048×1536 (aspect ratio preserved) |
| RS-3 | Image too tall resized down | Upload 2000×4000 JPEG | Saved at 1024×2048 (aspect ratio preserved) |
| RS-4 | Square image ratio preserved | Upload 3000×3000 JPEG | Saved at 2048×2048 |
| RS-5 | Small image not upscaled | Upload 100×80 JPEG | Saved at 100×80 (no upscale) |
| RS-6 | Non-image bytes handled | Upload random binary | 422, validation error |

### 2.3 Dedup

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| DD-1 | Same SHA256 returns existing | Upload same bytes twice | Second call returns data (not error) from DB lookup |
| DD-2 | Different bytes upload OK | Upload two different images | Both succeed, different sha256 values |

### 2.4 Thumbnail Generation

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| TN-1 | Thumbnail created after upload | Upload valid JPEG | Thumbnail stored at `..._thumb.jpg` |
| TN-2 | Thumbnail path in response | Check `thumbnail_url` field | Present and points to `/api/v1/photos/{sha256}/thumb.jpg` |

### 2.5 Error Handling

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| EH-1 | MinIO unavailable returns 503 | Mock MinIO to raise | 503 response, graceful message |
| EH-2 | DB error returns 500 | Force DB write failure | 500 response, logged error |

### 2.6 Service Layer

| ID | Title | Steps | Expected |
|----|-------|-------|----------|
| SV-1 | `resize_image()` dimensions correct | Call with 4000×3000 bytes | Returns bytes, output width ≤ 2048 |
| SV-2 | `resize_image()` skips small images | Call with 800×600 bytes | Returns same bytes (no resize) |
| SV-3 | `resize_image()` returns JPEG | Call with PNG bytes | Output is JPEG (starts with `\xff\xd8`) |

---

## 3. Test Data

- Test JPEG fixture: 200×150 solid red image (3KB)
- Test PNG fixture: 200×150 transparent image 
- Test WebP fixture: 200×150 image
- Test large JPEG: 4096×3072 (generate programmatically)
- Test binary non-image: 1KB random bytes

---

## 4. Quality Gates

- All UP, RS, DD, TN, EH, SV test IDs pass
- `ruff check .` — no warnings
- `mypy . --strict` — no errors
- `pytest tests/ -v --cov=. --cov-fail-under=80` — coverage ≥ 80%
