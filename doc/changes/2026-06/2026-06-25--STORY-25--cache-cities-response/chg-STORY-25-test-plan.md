# STORY-25 — Test Plan

**workItemRef:** STORY-25
**File:** `src/real-estate-api/tests/test_cities.py`

---

## Test Cases

### TC-1: Basic response format
- **Test:** `test_cities_endpoint_returns_list`
- **Setup:** Insert 3 properties in different cities (Warszawa, Kraków, Wrocław)
- **Assert:** Response `200`, body is a JSON array, each element has `city` and `count` fields
- **Assert:** Cities are sorted alphabetically
- **Assert:** `X-Cache` header is present

### TC-2: Cache miss then hit
- **Test:** `test_cities_cache_miss_then_hit`
- **Setup:** Insert 2 properties, clear cache
- **Assert (attempt 1):** `X-Cache: miss`
- **Assert (attempt 2):** `X-Cache: hit`
- **Assert:** Both responses have identical body

### TC-3: Redis fallback
- **Test:** `test_cities_cache_fallback`
- **Setup:** Mock Redis to raise exception or mark as unhealthy
- **Assert:** Response `200`, `X-Cache: miss (fallback)`, body is correct

### TC-4: Empty database
- **Test:** `test_cities_empty_db`
- **Setup:** No properties in database
- **Assert:** Response `200`, body is `[]`

### TC-5: Correct cache key
- **Test:** `test_cities_cache_key_is_cities_list`
- **Setup:** Spy on `redis.get` / `redis.set` to capture the key used
- **Assert:** Key equals `cities:list`

---

## Fixtures Needed (in conftest.py or test file)

- `test_db` with a few properties in different cities
- `redis_client` mock/fake (already exists in conftest.py)

---

## Quality Gates

- `ruff check .` — pass
- `mypy . --strict` — pass
- `pytest tests/ -v` — all test cases pass
