# Test Plan: STORY-29 — CDN-Friendly Photo URL (IMG-2)

**ref:** STORY-29
**status:** draft

---

## 1. Automated Tests

### 1.1 Test File: `src/real-estate-api/tests/test_photos.py`

| Test | Description |
|------|-------------|
| `test_get_photo_returns_200` | Valid SHA256 returns 200 with image/jpeg content type |
| `test_get_photo_cache_headers` | Response includes Cache-Control: public, max-age=31536000, immutable |
| `test_get_photo_etag_header` | Response includes ETag header matching the SHA256 |
| `test_get_photo_304_not_modified` | Request with matching If-None-Match returns 304 |
| `test_get_photo_404_not_found` | Non-existent SHA256 returns 404 |
| `test_get_photo_422_invalid_hash` | Invalid SHA256 format (not 64 hex) returns 422 |
| `test_get_photo_content_length` | Response includes Content-Length header |

### 1.2 Mock Setup

```python
@pytest.fixture
async def mock_minio():
    """Mock MinioStorageClient for photo serving tests."""
    # Return a fake photo for valid SHA256
    # Raise MinioException for invalid SHA256
```

---

## 2. Manual Verification

```bash
# 1. Start the stack
docker compose up -d minio real-estate-api

# 2. Test a photo URL (replace with a real SHA256 from your MinIO)
curl -v http://localhost:8000/api/v1/photos/abc123...456.jpg

# Verify:
#   HTTP/1.1 200 OK
#   Content-Type: image/jpeg
#   Cache-Control: public, max-age=31536000, immutable
#   ETag: "abc123...456"

# 3. Test 304
curl -v -H 'If-None-Match: "abc123...456"' http://localhost:8000/api/v1/photos/abc123...456.jpg
# Should return 304 Not Modified

# 4. Test 404
curl -v http://localhost:8000/api/v1/photos/0000000000000000000000000000000000000000000000000000000000000000.jpg
# Should return 404

# 5. Test 422
curl -v http://localhost:8000/api/v1/photos/invalid.jpg
# Should return 422
```

---

## 3. Verification Checklist

| AC | Test | Manual |
|----|------|--------|
| AC-1 | `test_get_photo_returns_200` | `curl` returns 200 + image data |
| AC-2 | `test_get_photo_cache_headers` | `curl -v` shows Cache-Control header |
| AC-3 | `test_get_photo_etag_header` | `curl -v` shows ETag header |
| AC-4 | `test_get_photo_304_not_modified` | `curl` with If-None-Match returns 304 |
| AC-5 | `test_get_photo_content_length` | `curl -v` shows Content-Length |
| AC-6 | `test_get_photo_404_not_found` | `curl` to non-existent returns 404 |
| AC-7 | Manual code review | `property_to_card` uses API URLs |
| AC-8 | `pytest tests/` | All existing tests pass |
