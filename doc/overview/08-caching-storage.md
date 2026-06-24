---
id: CACHE-OVERVIEW
status: Draft
created: 2026-06-22
last_updated: 2026-06-22
owners: ["rendenwald"]
summary: "Redis Cache and MinIO Storage overview — cache strategy, image pipeline, secrets management."
---

# Redis Cache & MinIO Storage Overview

> **Source:** Derived from `specs/120-CACHING-STORAGE.md`, `specs/080-API.md`, `specs/060-SCRAPER-BASE.md`.

---

## Overview

Redis 7 (maxmemory 1GB, allkeys-lru, no persist) serves as the cache layer (cache-aside pattern) and message broker (Redis Streams for alert delivery). MinIO (standalone, 200Gi volume) stores property photos, user avatars, portal logos, and reports. An image processing pipeline validates, resizes, deduplicates (SHA256), and stores photos with 400×300 thumbnails.

## Key Capabilities

- **Cache-aside** — 5 cached endpoints with tiered TTLs (2 min to 24h)
- **Cache invalidation** — Direct Redis SCAN + DEL from `scrapper-base` after each property upsert (STORY-24); fire-and-forget, graceful degradation
- **Redis Streams** — `stream:new_property` and `stream:alerts:pending` with MAXLEN caps and dead-letter queue (planned)
- **MinIO buckets** — `property-photos`, `user-avatars`, `portal-logos`, `reports`
- **Image pipeline** — Validation → resize (original + thumbnail) → SHA256 dedup → MinIO store
- **Secrets management** — Kubernetes Secrets via `secretKeyRef`, bucket-level RBAC policies

## Architecture

### Cache Strategy Matrix

| Key Pattern | TTL | Populated By | Invalidated By |
|-------------|-----|-------------|----------------|
| `properties:list:v1:{hash}` | 120s | API GET /properties | New property upsert (via `CacheInvalidator`) |
| `properties:detail:{id}` | 300s | API GET /properties/{id} | Property update (via `CacheInvalidator`) |
| `cities:list` | 3600s | API GET /cities | New property upsert (via `CacheInvalidator`) |
| `stats:platform` | 900s | API GET /stats | Dedup run |
| `rates:ecb:{date}` | 86400s | Daily CronJob | Time-based expiry |

### Cache Invalidation (STORY-24)

Cache invalidation is performed **directly from `scrapper-base`** after each successful
property upsert, using the ``CacheInvalidator`` class in ``scraper_base.cache_invalidator``:

- **On insert** (``is_new=True``): SCAN ``properties:list:v1:*`` → DEL all matched keys + DEL ``cities:list``
- **On update** (``is_new=False``): DEL ``properties:detail:{id}`` only

The invalidator connects to Redis via ``REDIS_URL`` env var. If not configured, or on
Redis error, invalidation is silently skipped (fire-and-forget). This is an MVP approach;
future iterations may use Redis Streams for decoupled invalidation.

### Redis Streams

- `scrapper-base` publishes to `stream:new_property` (MAXLEN 10k) and `stream:price_change` *(planned — not yet implemented)*
- Alert Worker consumes via `XREADGROUP`, processes matches, publishes to `stream:alerts:pending` (MAXLEN 5k)
- Email Worker consumes from `stream:alerts:pending`
- Dead-letter stream `stream:dead_letter` holds failed messages for 7 days

### Image Processing Pipeline

```
Upload/Scrape → Validation (type, size) → Resize (original + 400×300 thumb)
    → SHA256 hash dedup → Store in property-photos bucket → Pre-signed URL (24h) → CDN
```

### MinIO Bucket RBAC

| Policy | Actions | Resources |
|--------|---------|-----------|
| `scraper-policy` | `s3:PutObject` | `property-photos/*` |
| `api-policy` | `s3:GetObject` | `property-photos/*`, `portal-logos/*` |
| `admin-policy` | `s3:*` | All buckets |

## Related Documents

- `specs/120-CACHING-STORAGE.md` — Full cache and storage specification
- `specs/080-API.md` — Cache-aside implementation in API services
- `specs/060-SCRAPER-BASE.md` — Stream publisher, MinIO photo upload
- `specs/070-DATABASE.md` — Photo assets table schema
- `doc/overview/02-architecture.md` — Storage namespace in k3s
