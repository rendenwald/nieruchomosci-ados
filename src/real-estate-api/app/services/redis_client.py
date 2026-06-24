"""
Async Redis client wrapper with connection pooling, health checks,
graceful degradation, and background recovery.

Uses ``redis.asyncio`` (official ``redis-py`` v5+) — no deprecated
``aioredis`` library.
"""

import asyncio
import random

import structlog
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError, TimeoutError

from app.core.config import get_settings
from app.core.metrics import cache_operation_duration_seconds, redis_degraded

logger = structlog.get_logger(__name__)


class RedisClient:
    """Async Redis client with connection pooling, health tracking,
    and background recovery.

    Attributes:
        healthy: Current health status (True = available, False = degraded).
        failure_count: Consecutive health-check failures.
    """

    def __init__(self) -> None:
        self._redis: AsyncRedis | None = None
        self._pool: ConnectionPool | None = None
        self.healthy: bool = True
        self.failure_count: int = 0
        self._settings = get_settings()
        self._log = logger.bind(service="redis")
        self._recovery_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Create the Redis connection pool and verify connectivity.

        Respects ``REDIS_ENABLED``: if ``False``, returns early without
        creating a pool. Starts the background recovery worker on exit
        (unless Redis is disabled).
        """
        if not self._settings.REDIS_ENABLED:
            self.healthy = False
            redis_degraded.set(0)
            self._log.warning("redis_disabled_by_config", healthy=False)
            return

        try:
            self._pool = ConnectionPool.from_url(
                self._settings.REDIS_URL,
                max_connections=self._settings.REDIS_POOL_SIZE,
                socket_connect_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                socket_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                decode_responses=True,
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            await self.ping()
            self.healthy = True
            self.failure_count = 0
            redis_degraded.set(0)
            self._log.info("redis_connected", healthy=True)
        except RedisError as exc:
            self.healthy = False
            self.failure_count += 1
            redis_degraded.set(1)
            self._log.warning(
                "redis_connection_failed",
                error=str(exc),
                healthy=False,
                recovery_worker_active=True,
            )

        await self._start_recovery_worker()

    async def disconnect(self) -> None:
        """Stop the recovery worker and close the Redis connection pool."""
        await self._stop_recovery_worker()
        if self._pool is not None:
            await self._pool.disconnect()
            self._log.info("redis_disconnected")

    async def ping(self) -> bool:
        """Health check with timeout.

        Updates ``redis_degraded`` gauge on state transitions.

        Returns:
            ``True`` if Redis responds, ``False`` otherwise.
        """
        if self._redis is None:
            return False
        try:
            result = await self._redis.ping()
            if result:
                was_degraded = not self.healthy
                self.healthy = True
                self.failure_count = 0
                if was_degraded:
                    redis_degraded.set(0)
                    self._log.warning("redis_recovered", healthy=True)
                return True
            return False
        except (RedisError, TimeoutError, OSError) as exc:
            self.failure_count += 1
            if self.failure_count >= self._settings.REDIS_HEALTH_CHECK_FAILURE_THRESHOLD:
                was_healthy = self.healthy
                self.healthy = False
                if was_healthy:
                    redis_degraded.set(1)
                    self._log.warning(
                        "redis_degraded",
                        failure_count=self.failure_count,
                        error=str(exc),
                    )
            return False

    async def _start_recovery_worker(self) -> None:
        """Start the background recovery worker task (idempotent)."""
        if self._recovery_task is not None:
            return
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        self._log.debug("recovery_worker_started")

    async def _stop_recovery_worker(self) -> None:
        """Cancel the background recovery worker task."""
        if self._recovery_task is not None and not self._recovery_task.done():
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        self._recovery_task = None
        self._log.debug("recovery_worker_stopped")

    async def _recovery_loop(self) -> None:
        """Background loop that pings degraded Redis and reconnects on recovery.

        Idles (sleeps) while Redis is healthy. When degraded, pings every
        ``REDIS_HEALTH_CHECK_INTERVAL`` (with ±10% jitter) and calls
        ``_reconnect_pool()`` on successful ping.
        """
        try:
            while True:
                if self.healthy:
                    await asyncio.sleep(self._settings.REDIS_HEALTH_CHECK_INTERVAL)
                    continue

                # Degraded — sleep with jitter then probe
                interval = self._settings.REDIS_HEALTH_CHECK_INTERVAL * (
                    0.9 + random.random() * 0.2
                )
                await asyncio.sleep(interval)
                try:
                    ok = await self.ping()
                    if ok:
                        await self._reconnect_pool()
                except Exception:  # noqa: BLE001
                    self._log.warning("recovery_loop_error", exc_info=True)
        except asyncio.CancelledError:
            self._log.debug("recovery_worker_cancelled")
            raise

    async def _reconnect_pool(self) -> None:
        """Reinitialise the Redis connection pool after degradation.

        Disconnects the old pool, creates a new one, and verifies
        connectivity with a ping.
        """
        self._log.info("redis_reconnecting")
        old_pool = self._pool

        try:
            self._pool = ConnectionPool.from_url(
                self._settings.REDIS_URL,
                max_connections=self._settings.REDIS_POOL_SIZE,
                socket_connect_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                socket_timeout=self._settings.REDIS_TIMEOUT_SECONDS,
                decode_responses=True,
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            ok = await self.ping()
            if ok:
                redis_degraded.set(0)
                self.healthy = True
                self.failure_count = 0
                self._log.info("redis_reconnected", healthy=True)
            else:
                self.healthy = False
                self._log.warning("redis_recovery_failed", healthy=False)
        except Exception as exc:  # noqa: BLE001
            self.healthy = False
            self._log.warning("redis_recovery_failed", error=str(exc))

        # Disconnect old pool after new one is set up
        if old_pool is not None:
            try:
                await old_pool.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def get(self, key: str) -> str | None:
        """GET a value from Redis.

        Args:
            key: The cache key to retrieve.

        Returns:
            The string value, or ``None`` if not found.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return None
        with cache_operation_duration_seconds.labels(
            endpoint="properties", operation="get",
        ).time():
            value: str | None = await self._redis.get(key)
            return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        """SET a value in Redis with TTL (SETEX semantics).

        Args:
            key: The cache key.
            value: The string value to store.
            ttl: Time-to-live in seconds.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return
        with cache_operation_duration_seconds.labels(
            endpoint="properties", operation="set",
        ).time():
            await self._redis.setex(key, ttl, value)

    async def set_nx(self, key: str, value: str, ttl: int) -> bool:
        """Set a key if it does not already exist (SET NX).

        Used for distributed locking to prevent thundering herd.

        Args:
            key: The lock key.
            value: The lock value (typically empty string).
            ttl: Lock TTL in seconds (short-lived, ~5s).

        Returns:
            ``True`` if the lock was acquired, ``False`` otherwise.

        Raises:
            RedisError: On Redis communication failure (caller handles).
        """
        if self._redis is None:
            return False
        result: bool = await self._redis.setnx(key, value)
        if result:
            await self._redis.expire(key, ttl)
        return result
