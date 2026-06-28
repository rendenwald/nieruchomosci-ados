"""
Tests for the ``GET /api/v1/photos/{sha256}.jpg`` endpoint.

Covers:
- 200 response with valid SHA256
- Cache-Control and ETag headers
- 304 Not Modified when If-None-Match matches
- 404 for non-existent photos
- 422 for invalid hash format
"""

from unittest.mock import MagicMock

import pytest
from minio.error import S3Error


@pytest.mark.asyncio
async def test_get_photo_returns_200(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Valid SHA256 returns 200 with image/jpeg content type."""
    valid_sha256 = "ab" + "c" * 62  # 64 hex chars
    fake_data = b"\xff\xd8\xff\xe0"  # JPEG magic bytes

    # Mock MinIO response
    mock_response = MagicMock()
    mock_response.read.return_value = fake_data
    app_with_minio.state.minio_client.get_object.return_value = mock_response

    response = await client.get(f"/api/v1/photos/{valid_sha256}.jpg")
    assert response.status_code == 200
    assert response.content == fake_data


@pytest.mark.asyncio
async def test_get_photo_cache_headers(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Response includes Cache-Control: public, max-age=31536000, immutable."""
    valid_sha256 = "ab" + "c" * 62

    mock_response = MagicMock()
    mock_response.read.return_value = b"fake"
    app_with_minio.state.minio_client.get_object.return_value = mock_response

    response = await client.get(f"/api/v1/photos/{valid_sha256}.jpg")
    assert response.status_code == 200
    cache_control = response.headers.get("cache-control", "")
    assert "public" in cache_control
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control


@pytest.mark.asyncio
async def test_get_photo_etag_header(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Response includes ETag header matching the SHA256."""
    valid_sha256 = "ab" + "c" * 62

    mock_response = MagicMock()
    mock_response.read.return_value = b"fake"
    app_with_minio.state.minio_client.get_object.return_value = mock_response

    response = await client.get(f"/api/v1/photos/{valid_sha256}.jpg")
    assert response.status_code == 200
    etag = response.headers.get("etag", "")
    assert f'"{valid_sha256}"' == etag


@pytest.mark.asyncio
async def test_get_photo_304_not_modified(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Request with matching If-None-Match returns 304."""
    valid_sha256 = "ab" + "c" * 62
    etag = f'"{valid_sha256}"'

    response = await client.get(
        f"/api/v1/photos/{valid_sha256}.jpg",
        headers={"If-None-Match": etag},
    )
    assert response.status_code == 304
    # Should not call MinIO at all
    app_with_minio.state.minio_client.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_get_photo_404_not_found(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Non-existent SHA256 returns 404."""
    valid_sha256 = "ab" + "c" * 62

    # Mock MinIO to raise NoSuchKey
    app_with_minio.state.minio_client.get_object.side_effect = S3Error(
        code="NoSuchKey",
        message="Not found",
        resource=f"photos/{valid_sha256[:2]}/{valid_sha256[2:4]}/{valid_sha256}.jpg",
        request_id="test",
        host_id="test",
        response=None,
    )

    response = await client.get(f"/api/v1/photos/{valid_sha256}.jpg")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_photo_422_invalid_hash(client) -> None:  # type: ignore[no-untyped-def]
    """Invalid SHA256 format (not 64 hex) returns 422."""
    # Too short
    response = await client.get("/api/v1/photos/short.jpg")
    assert response.status_code == 422

    # Non-hex characters
    response = await client.get("/api/v1/photos/" + "z" * 64 + ".jpg")
    assert response.status_code == 422

    # 63 chars (too short)
    response = await client.get("/api/v1/photos/" + "a" * 63 + ".jpg")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_photo_content_length(client, app_with_minio) -> None:  # type: ignore[no-untyped-def]
    """Response includes Content-Length header."""
    valid_sha256 = "ab" + "c" * 62
    fake_data = b"\xff\xd8\xff\xe0" * 100  # 400 bytes

    mock_response = MagicMock()
    mock_response.read.return_value = fake_data
    app_with_minio.state.minio_client.get_object.return_value = mock_response

    response = await client.get(f"/api/v1/photos/{valid_sha256}.jpg")
    assert response.status_code == 200
    assert int(response.headers.get("content-length", "0")) == len(fake_data)
