"""
Photo serving endpoint with CDN-friendly cache headers.

``GET /api/v1/photos/{sha256}.jpg`` — serves a photo from MinIO with
immutable caching headers for optimal CDN caching.

Photos are stored in MinIO using SHA256-based content addressing:
``property-photos/photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg``
"""

import asyncio
import re

import structlog
from fastapi import APIRouter, Request, Response
from minio import Minio
from minio.error import MinioException, S3Error

logger = structlog.get_logger(__name__)

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

router = APIRouter(prefix="/photos", tags=["photos"])


def _validate_sha256(sha256: str) -> str | None:
    """Validate and normalise a SHA-256 hex digest.

    Returns the lowercased digest if valid, ``None`` otherwise.
    """
    normalized = sha256.lower()
    if SHA256_PATTERN.match(normalized):
        return normalized
    return None


def _get_minio_client(request: Request) -> Minio | None:
    """Return the MinIO client from app state, or ``None`` if unavailable."""
    client: Minio | None = getattr(request.app.state, "minio_client", None)
    return client


@router.get("/{sha256}.jpg")
async def get_photo(sha256: str, request: Request) -> Response:
    """Serve a photo from MinIO with CDN-friendly cache headers.

    Args:
        sha256: SHA-256 hex digest of the photo.
        request: The FastAPI request object (for app state and headers).

    Returns:
        - ``200`` with the photo binary and cache headers.
        - ``304`` if ``If-None-Match`` matches the SHA256.
        - ``404`` if the photo is not found.
        - ``422`` if the SHA256 format is invalid.

    """
    # Validate SHA256 format
    normalized = _validate_sha256(sha256)
    if not normalized:
        return Response(
            status_code=422,
            content='{"detail": "Invalid SHA256 hash"}',
            media_type="application/json",
        )

    # Construct the MinIO object path
    object_path = f"photos/{normalized[:2]}/{normalized[2:4]}/{normalized}.jpg"
    etag_value = f'"{normalized}"'

    # Check If-None-Match for 304
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag_value:
        return Response(
            status_code=304,
            headers={
                "ETag": etag_value,
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    # Get MinIO client
    client = _get_minio_client(request)
    if client is None:
        logger.warning("MinIO client unavailable for photo request", sha256=normalized)
        return Response(
            status_code=404,
            content='{"detail": "Photo not found"}',
            media_type="application/json",
        )

    # Fetch from MinIO (wrapped in asyncio.to_thread since minio is sync)
    bucket: str = getattr(request.app.state, "minio_bucket", "property-photos")
    try:
        response = await asyncio.to_thread(
            client.get_object,
            bucket_name=bucket,
            object_name=object_path,
        )
        data: bytes = response.read()
        content_length = len(data)
        response.close()
        response.release_conn()
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            logger.debug("Photo not found in MinIO", sha256=normalized)
            return Response(
                status_code=404,
                content='{"detail": "Photo not found"}',
                media_type="application/json",
            )
        logger.warning("MinIO get_object failed", sha256=normalized, error=str(exc))
        return Response(
            status_code=404,
            content='{"detail": "Photo not found"}',
            media_type="application/json",
        )
    except MinioException as exc:
        logger.warning("MinIO error serving photo", sha256=normalized, error=str(exc))
        return Response(
            status_code=404,
            content='{"detail": "Photo not found"}',
            media_type="application/json",
        )

    # Return photo with cache headers
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


@router.get("/{sha256}/thumb.jpg")
async def get_thumbnail(sha256: str, request: Request) -> Response:
    """Serve a photo thumbnail from MinIO with CDN-friendly cache headers.

    Args:
        sha256: SHA-256 hex digest of the original photo.
        request: The FastAPI request object (for app state and headers).

    Returns:
        - ``200`` with the thumbnail binary and cache headers.
        - ``304`` if ``If-None-Match`` matches.
        - ``404`` if the thumbnail is not found.
        - ``422`` if the SHA256 format is invalid.

    """
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
        logger.warning("MinIO client unavailable for thumbnail request", sha256=normalized)
        return Response(
            status_code=404,
            content='{"detail": "Thumbnail not found"}',
            media_type="application/json",
        )

    bucket = getattr(request.app.state, "minio_bucket", "property-photos")
    try:
        response = await asyncio.to_thread(
            client.get_object,
            bucket_name=bucket,
            object_name=object_path,
        )
        data = response.read()
        content_length = len(data)
        response.close()
        response.release_conn()
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            logger.debug("Thumbnail not found in MinIO", sha256=normalized)
            return Response(
                status_code=404,
                content='{"detail": "Thumbnail not found"}',
                media_type="application/json",
            )
        logger.warning("MinIO get_object failed for thumbnail", sha256=normalized, error=str(exc))
        return Response(
            status_code=404,
            content='{"detail": "Thumbnail not found"}',
            media_type="application/json",
        )
    except MinioException as exc:
        logger.warning("MinIO error serving thumbnail", sha256=normalized, error=str(exc))
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
