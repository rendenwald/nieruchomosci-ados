"""
Application configuration using pydantic-settings.

All settings are loaded from environment variables with sensible defaults
for local development. In production, all values are configured via the
environment (typically from a Kubernetes ``ConfigMap`` / ``Secret``).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Attributes:
        REDIS_URL: Redis connection string.
        REDIS_POOL_SIZE: Maximum connections in the Redis pool.
        REDIS_TIMEOUT_SECONDS: Timeout for Redis operations.
        REDIS_HEALTH_CHECK_INTERVAL: Seconds between Redis health checks.
        REDIS_HEALTH_CHECK_FAILURE_THRESHOLD: Consecutive failures before degraded mode.
        DATABASE_URL: Async PostgreSQL connection string.
        DB_POOL_SIZE: Database connection pool size.
        CACHE_TTL_SECONDS: Default TTL for cached responses.
        API_PREFIX: Base path for API routes.
        PROPERTIES_MAX_LIMIT: Hard upper bound for pagination limit.
        PROPERTIES_DEFAULT_LIMIT: Default items per page.
        METRICS_ENABLED: If True, expose Prometheus metrics.
        CACHE_KEY_PREFIX: Prefix for Redis cache keys.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", frozen=True)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 10
    REDIS_TIMEOUT_SECONDS: int = 2
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_HEALTH_CHECK_FAILURE_THRESHOLD: int = 3
    REDIS_ENABLED: bool = True  # Whether to initialise Redis at startup
    REDIS_STARTUP_GRACE_PERIOD: int = 30  # Seconds after startup before /ready reports degraded Redis as not-ready

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/realestate"
    DB_POOL_SIZE: int = 5

    # Cache
    CACHE_TTL_SECONDS: int = 120
    CACHE_KEY_PREFIX: str = "properties:list:v1"

    # API
    API_PREFIX: str = "/api/v1"
    PROPERTIES_MAX_LIMIT: int = 100
    PROPERTIES_DEFAULT_LIMIT: int = 20

    # Observability
    METRICS_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of ``Settings``.

    Uses ``functools.lru_cache`` so that only one instance is created and
    reused for the application lifetime. Environment variables are read
    once at first call.

    Returns:
        The application ``Settings`` instance.

    """
    return Settings()
