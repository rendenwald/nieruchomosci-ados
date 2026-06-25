# STORY-25 — Cache `/api/v1/cities` Response for 1 Hour

**workItemRef:** STORY-25
**Epic:** 5 — Redis Cache
**Module Specs:** [080-API.md](../../../../specs/specs/080-API.md), [120-CACHING-STORAGE.md](../../../../specs/specs/120-CACHING-STORAGE.md)
**Status:** specification

---

## Problem

The `/api/v1/cities` endpoint queries the database on every request:
```sql
SELECT city, COUNT(*) as count
FROM properties
WHERE is_active = true AND is_canonical=true
GROUP BY city
ORDER BY city
```

City data changes infrequently (only when new properties are scraped), yet every page load re-executes this aggregation query. This is wasteful and increases DB load unnecessarily.

## Goals

1. Serve `GET /api/v1/cities` from Redis cache (TTL 1 hour / 3600s).
2. Return `X-Cache: hit|miss` header for observability.
3. Follow the existing cache-aside pattern from `GET /api/v1/properties`.
4. Existing cache invalidation from STORY-24 already handles `cities:list` key.
5. Graceful degradation: fall back to DB query when Redis is unavailable.

## Non-Goals

- No cache invalidation logic (already handled by STORY-24 — property upserts delete `cities:list`).
- No schema changes needed (the DB query returns simple `{city, count}` rows).
- No new configuration values — reuses `CACHE_TTL_SECONDS` default with an explicit 3600s TTL override.

## Scope

### Files to create

| File | Purpose |
|------|---------|
| `src/real-estate-api/app/routers/cities.py` | `GET /api/v1/cities` router |
| `src/real-estate-api/app/schemas/city.py` | `CityCount` response schema |
| `src/real-estate-api/tests/test_cities.py` | Tests for the cities endpoint |

### Files to modify

| File | Change |
|------|--------|
| `src/real-estate-api/app/main.py` | Register `cities.router` |
| `src/real-estate-api/app/services/cache_service.py` | Make `_endpoint` and `_key_prefix` configurable per call (replace hardcoded init-time values with call-time parameters) |
| `src/real-estate-api/app/core/config.py` | Add `CITIES_CACHE_KEY_PREFIX` and `CITIES_CACHE_TTL` settings |
| `src/real-estate-api/app/routers/properties.py` | Update to use new CacheService signature |

## Acceptance Criteria

1. `GET /api/v1/cities` returns `200` with JSON body `[{"city": "Warszawa", "count": 1523}, ...]`.
2. First request returns `X-Cache: miss` header. Subsequent requests within 3600s return `X-Cache: hit`.
3. City data is sorted alphabetically by city name.
4. When Redis is unavailable, request succeeds with `X-Cache: miss (fallback)` and correct data.
5. `cities:list` cache key is used (per spec 120-CACHING-STORAGE.md).
6. All existing tests still pass. New tests cover cache hit, cache miss, and Redis fallback.

## API Specification

```
GET /api/v1/cities
Response 200:
[
  {"city": "Warszawa", "count": 1523},
  {"city": "Kraków", "count": 892},
  {"city": "Wrocław", "count": 654}
]
Headers:
  X-Cache: hit | miss | miss (fallback)
  Content-Type: application/json
```

## Risks & Dependencies

- None. This is a straightforward application of the existing cache-aside pattern.
- STORY-24 (already done) handles cache invalidation of `cities:list` on property upsert.

## Cache Strategy

| Setting | Value |
|---------|-------|
| Cache key | `cities:list` |
| TTL | 3600s (1 hour) |
| Populated by | `GET /api/v1/cities` on cache miss |
| Invalidated by | New property upsert (STORY-24) |

## Edge Cases

- Empty database: returns `[]` (no cities found).
- Database connection failure: returns `[]` with `X-Cache: miss (fallback)`.
- Redis error during compute+store: falls back to DB query, returns data with `X-Cache: miss (fallback)`.
