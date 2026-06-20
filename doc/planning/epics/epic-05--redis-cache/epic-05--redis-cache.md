# Epic 05: Redis Cache

> **Goal:** Implement Redis-based caching layer for API responses with cache-aside pattern, cache invalidation on new data, and graceful degradation.

## Scope

- Redis 7 configuration (maxmemory 1GB, allkeys-lru)
- Cache-aside pattern for API endpoints
- Cache invalidation on property upsert
- Redis Streams for real-time event processing
- Graceful fallback when Redis is unavailable

## Success Criteria

- API responses served from Redis within TTL
- New scraped properties invalidate affected cache keys
- System continues operating when Redis is down (fallback to DB)

## Related Spec Modules

- `specs/120-CACHING-STORAGE.md`
- `specs/080-API.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-23 | Serve `/api/v1/properties` from Redis cache (TTL 2min) |
| STORY-24 | Invalidate relevant cache keys on new property scrape |
| STORY-25 | Cache `/api/v1/cities` response for 1 hour |
| STORY-26 | Use Redis Streams for real-time alert delivery |
| STORY-27 | Graceful fallback to direct DB query when Redis unavailable |
