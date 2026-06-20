"""Tests for MinIO storage client."""

from scraper_base.storage import MAX_PHOTOS_PER_PROPERTY, MinioStorageClient


class TestMinioStorageClient:
    """MinioStorageClient behaviour."""

    async def test_init_from_env(self, monkeypatch):
        """Client reads config from environment variables."""
        monkeypatch.setenv("MINIO_ENDPOINT", "minio.example.com:9000")
        monkeypatch.setenv("MINIO_ACCESS_KEY", "testkey")
        monkeypatch.setenv("MINIO_SECRET_KEY", "testsecret")
        monkeypatch.setenv("MINIO_BUCKET", "test-bucket")

        client = MinioStorageClient()
        assert client._endpoint == "minio.example.com:9000"
        assert client._access_key == "testkey"
        assert client._secret_key == "testsecret"
        assert client._bucket == "test-bucket"
        assert client.is_available is False  # Not connected yet

    async def test_init_defaults(self):
        """Client has sensible default values."""
        client = MinioStorageClient()
        assert client._endpoint == "localhost:9000"
        assert client._bucket == "property-photos"

    async def test_ensure_bucket_graceful_degradation(self):
        """ensure_bucket returns False when MinIO is unavailable."""
        client = MinioStorageClient(endpoint="localhost:1")
        result = await client.ensure_bucket("test-bucket")
        assert result is False
        assert client.is_available is False

    async def test_upload_graceful_degradation(self):
        """upload_photo returns None when MinIO is unavailable."""
        client = MinioStorageClient(endpoint="localhost:1")
        result = await client.upload_photo(b"test data", "test/photo.jpg")
        assert result is None

    async def test_get_photo_url_graceful_degradation(self):
        """get_photo_url returns None when MinIO is unavailable."""
        client = MinioStorageClient(endpoint="localhost:1")
        result = await client.get_photo_url("test/photo.jpg")
        assert result is None

    def test_max_photos_constant(self):
        """MAX_PHOTOS_PER_PROPERTY is set."""
        assert MAX_PHOTOS_PER_PROPERTY == 20
