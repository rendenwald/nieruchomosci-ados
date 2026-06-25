# STORY-25 — Implementation Plan

**workItemRef:** STORY-25
**Status:** plan

---

## Phase 1: Config — `app/core/config.py`

**Goal:** Add cities-specific cache settings.

**Changes:**
- Add `CITIES_CACHE_TTL: int = 3600` (1 hour)
- Add `CITIES_CACHE_KEY_PREFIX: str = "cities:list"`

## Phase 2: CacheService — `app/services/cache_service.py`

**Goal:** Make `_endpoint` and `_key_prefix` configurable per `get_or_compute()` call, not hardcoded at init.

**Changes:**
- Add `endpoint: str = "properties"` and `key_prefix: str | None = None` parameters to `get_or_compute()`
- Use `key_prefix or self._key_prefix` for metrics labels
- Use `endpoint` parameter instead of `self._endpoint` in metrics labels
- Update all internal `_endpoint` references to use the passed `endpoint` parameter
- Keep backward compatibility by providing defaults

## Phase 3: City Schema — `app/schemas/city.py`

**Goal:** Pydantic model for the response.

**Content:**
```python
from pydantic import BaseModel

class CityCount(BaseModel):
    city: str
    count: int
```

## Phase 4: City Router — `app/routers/cities.py`

**Goal:** `GET /api/v1/cities` endpoint with cache-aside.

**Pattern:** Follow `properties.py` exactly — same cache_aside via `CacheService.get_or_compute()`.

**DB Query:**
```sql
SELECT city, COUNT(*) as count
FROM properties
WHERE is_active = true AND is_canonical = true
GROUP BY city
ORDER BY city
```

**Cache Config:**
- Key: `cities:list`
- TTL: 3600s (from `settings.CITIES_CACHE_TTL`)
- Endpoint label: `cities`
- Key prefix label: `cities:list`

**Response:** `list[CityCount]` JSON array.

**X-Cache header:** Same as properties.py — set via `Response` headers dict.

## Phase 5: Main — `app/main.py`

**Goal:** Register the cities router.

**Change:** Add `from app.routers import cities` and `app.include_router(cities.router, prefix=settings.API_PREFIX)`.

## Phase 6: Properties Router Update — `app/routers/properties.py`

**Goal:** Update `get_or_compute()` call to pass new `endpoint` and `key_prefix` parameters.

**Change:** Call `cache_service.get_or_compute(key=cache_key, compute=query_db, ttl=..., endpoint="properties", key_prefix=settings.CACHE_KEY_PREFIX)`

## Phase 7: Tests — `tests/test_cities.py`

**Goal:** Test `GET /api/v1/cities` with cache hit, miss, and fallback.

**Test cases:**
1. `test_cities_endpoint_returns_list` — basic response format
2. `test_cities_cache_miss_then_hit` — first request is miss, second is hit
3. `test_cities_cache_fallback` — when Redis unavailable, returns data with miss (fallback)
4. `test_cities_empty_db` — returns `[]` when no properties
5. `test_cities_cache_key_is_cities_list` — verify cache key `cities:list` is used

## Phase 8: Quality Gates

- `ruff check .` — no new lint warnings
- `mypy . --strict` — no new type errors
- `pytest tests/ -v` — all tests pass
