"""
MinIO storage client for photo upload/download.

Provides ``MinioStorageClient`` with SHA256-based object naming and graceful
degradation when MinIO is unavailable.
"""

import hashlib
import logging
import os

from minio import Minio

logger = logging.getLogger(__name__)

# Hard cap enforced before upload (per 070-DATABASE.md FIX-10)
MAX_PHOTOS_PER_PROPERTY: int = 20


class MinioStorageError(Exception):
    """Raised when a critical MinIO operation fails."""


class MinioStorageClient:
    """Client for interacting with MinIO object storage.

    Configured via environment variables:
    - ``MINIO_ENDPOINT`` — e.g. ``localhost:9000``
    - ``MINIO_ACCESS_KEY`` — access key (user)
    - ``MINIO_SECRET_KEY`` — secret key (password)
    - ``MINIO_BUCKET`` — bucket name (default: ``"property-photos"``)
    - ``MINIO_SECURE`` — use HTTPS (default: ``"false"``)

    If MinIO is unreachable or misconfigured, all operations log a warning
    and degrade gracefully (return ``None`` / empty results).
    """

    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
    ) -> None:
        self._endpoint = endpoint or os.environ.get("MINIO_ENDPOINT", "localhost:9000")
        key = access_key or os.environ.get("MINIO_ACCESS_KEY")
        if not key:
            msg = "MINIO_ACCESS_KEY must be set via env var or access_key parameter"
            raise ValueError(msg)
        secret = secret_key or os.environ.get("MINIO_SECRET_KEY")
        if not secret:
            msg = "MINIO_SECRET_KEY must be set via env var or secret_key parameter"
            raise ValueError(msg)
        self._access_key = key
        self._secret_key = secret
        self._bucket = bucket or os.environ.get("MINIO_BUCKET", "property-photos")
        if secure is None:
            raw = os.environ.get("MINIO_SECURE", "false")
            self._secure = raw.lower() in ("1", "true", "yes")
        else:
            self._secure = secure

        self._client: Minio | None = None
        self._available: bool = False
        self._initialised: bool = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def ensure_bucket(self, bucket: str | None = None) -> bool:
        """Ensure the configured bucket exists, creating it if necessary.

        Args:
            bucket: Override the default bucket name.

        Returns:
            ``True`` if the bucket exists or was created, ``False`` on
            graceful degradation.

        """
        target_bucket = bucket or self._bucket
        client = self._get_client()
        if client is None:
            return False
        try:
            if not client.bucket_exists(target_bucket):
                client.make_bucket(target_bucket)
                logger.info("Created MinIO bucket", extra={"bucket": target_bucket})
            else:
                logger.debug("MinIO bucket exists", extra={"bucket": target_bucket})
            self._available = True
            return True
        except Exception as exc:
            logger.warning(
                "MinIO bucket operation failed",
                extra={"bucket": target_bucket, "error": str(exc)},
            )
            self._available = False
            return False

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload_photo(
        self,
        data: bytes,
        object_name: str | None = None,
        content_type: str = "image/jpeg",
    ) -> str | None:
        """Upload a photo to MinIO.

        If ``object_name`` is not provided, a SHA256 hash of the data is used
        (ensuring content-based deduplication).

        Args:
            data: Raw photo bytes.
            object_name: Optional object name (path). Auto-generated if omitted.
            content_type: MIME type of the photo (default ``image/jpeg``).

        Returns:
            The object name (path) on success, or ``None`` if MinIO is
            unavailable.

        """
        if not self._available and self._initialised:
            logger.warning("MinIO unavailable, skipping photo upload")
            return None

        if object_name is None:
            sha256 = hashlib.sha256(data).hexdigest()
            object_name = f"photos/{sha256[:2]}/{sha256[2:4]}/{sha256}.jpg"

        client = self._get_client()
        if client is None:
            return None

        try:
            client.put_object(
                bucket_name=self._bucket,
                object_name=object_name,
                data=__import__("io").BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            logger.info(
                "Photo uploaded",
                extra={"object_name": object_name, "size_bytes": len(data)},
            )
            return object_name
        except Exception as exc:
            logger.warning(
                "Photo upload failed",
                extra={"object_name": object_name, "error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # Download URL
    # ------------------------------------------------------------------

    async def get_photo_url(
        self,
        object_name: str,
        expires_seconds: int = 3600,
    ) -> str | None:
        """Generate a presigned GET URL for a photo.

        Args:
            object_name: The object path in the bucket.
            expires_seconds: URL validity in seconds (default 1 hour).

        Returns:
            A temporary URL, or ``None`` if MinIO is unavailable.

        """
        client = self._get_client()
        if client is None:
            return None
        try:
            url = client.presigned_get_object(
                bucket_name=self._bucket,
                object_name=object_name,
                expires=__import__("datetime").timedelta(seconds=expires_seconds),
            )
            return str(url)
        except Exception as exc:
            logger.warning(
                "Failed to generate presigned URL",
                extra={"object_name": object_name, "error": str(exc)},
            )
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self) -> Minio | None:
        """Return the MinIO client or ``None`` if unavailable."""
        if self._client is None:
            try:
                self._client = Minio(
                    endpoint=self._endpoint,
                    access_key=self._access_key,
                    secret_key=self._secret_key,
                    secure=self._secure,
                )
                self._available = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MinIO client creation failed",
                    extra={"error": str(exc)},
                )
                self._available = False
        self._initialised = True
        if not self._available:
            return None
        return self._client

    @property
    def is_available(self) -> bool:
        """Return ``True`` if MinIO is currently reachable."""
        return self._available

    @property
    def bucket(self) -> str:
        """Return the configured bucket name."""
        return self._bucket
