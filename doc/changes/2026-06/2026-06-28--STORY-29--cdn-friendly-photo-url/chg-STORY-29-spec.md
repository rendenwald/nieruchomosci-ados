# Specification: STORY-29 — CDN-Friendly Photo URL (IMG-2)

**ref:** STORY-29
**epic:** Epic 6 — Photo Storage (IMG-2)
**spec module:** `120-CACHING-STORAGE.md`
**status:** draft

---

## 1. Problem

Photos stored in MinIO are currently accessed via presigned URLs generated
by `MinioStorageClient.get_photo_url()`. These URLs:
- Expire after 1 hour (causing broken images on stale pages)
- Are not cacheable by CDNs (different URL each time)
- Leak MinIO internal paths and credentials

---

## 2. Goals

1. Provide a stable, CDN-friendly URL pattern for photos:
   `GET /api/v1/photos/{sha256}.jpg`
2. Serve photos with cache headers allowing long-lived CDN caching:
   `Cache-Control: public, max-age=31536000, immutable`
3. Support ETag/If-None-Match for 304 Not Modified responses
4. Update `PropertyCard.photos` to use the new URL pattern

---

## 3. Acceptance Criteria

| ID | Criteria |
|----|----------|
| AC-1 | `GET /api/v1/photos/{sha256}.jpg` returns the photo with `Content-Type: image/jpeg` |
| AC-2 | Response includes `Cache-Control: public, max-age=31536000, immutable` |
| AC-3 | Response includes `ETag: "{sha256}"` header |
| AC-4 | Request with `If-None-Match: "{sha256}"` returns `304 Not Modified` |
| AC-5 | Response includes `Content-Length` header |
| AC-6 | 404 returned when the photo does not exist in MinIO |
| AC-7 | `PropertyCard.photos` uses the new `/api/v1/photos/` URL format instead of presigned MinIO URLs |
| AC-8 | All existing tests continue to pass (`pytest`, `ruff`, `mypy`) |

---

## 4. Non-Goals

- No thumbnail generation (separate story: STORY-31)
- No photo upload endpoint (separate story: STORY-30)
- No photo deletion (separate story: STORY-32)
- No SvelteKit frontend changes
- No Cloudflare or actual CDN configuration

---

## 5. Scope

### 5.1 Files to Create

| File | Purpose |
|------|---------|
| `src/real-estate-api/app/routers/photos.py` | Photo serving endpoint |

### 5.2 Files to Modify

| File | Change |
|------|--------|
| `src/real-estate-api/app/main.py` | Register `photos` router |
| `src/real-estate-api/app/services/property_service.py` | Update `property_to_card` to use API URLs |
| `src/real-estate-api/app/schemas/__init__.py` | Export photo schemas |
| `src/real-estate-api/tests/test_photos.py` | New test file |
| `src/real-estate-api/tests/conftest.py` | Add MinIO fixtures |

---

## 6. API Design

```
GET /api/v1/photos/{sha256}.jpg
```

Path parameters:
- `sha256` — SHA-256 hex digest of the photo content (64 hex chars)

Response (200):
```http
HTTP/1.1 200 OK
Content-Type: image/jpeg
Content-Length: 123456
Cache-Control: public, max-age=31536000, immutable
ETag: "abc123..."
Accept-Ranges: bytes

<binary image data>
```

Response (304):
```http
HTTP/1.1 304 Not Modified
ETag: "abc123..."
Cache-Control: public, max-age=31536000, immutable
```

Response (404):
```json
{
  "detail": "Photo not found"
}
```

---

## 7. Dependencies

- MinIO must be running and accessible
- The photo must exist at `property-photos/photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg`

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Large photo files consume API memory | Stream from MinIO using `StreamingResponse` |
| MinIO unavailable returns 500 to user | Fallback to 404 if MinIO is unreachable |
