# STORY-26 — Use Redis Streams for Real-Time Alert Delivery

**workItemRef:** STORY-26
**Epic:** 5 — Redis Cache
**Module Specs:** [120-CACHING-STORAGE.md](../../../../specs/specs/120-CACHING-STORAGE.md), [130-MONITORING-ALERTS.md](../../../../specs/specs/130-MONITORING-ALERTS.md)
**Status:** specification

---

## Problem

When a scraper discovers a new or updated property, the system currently:
1. Persists the property to the database
2. Invalidates Redis cache keys (STORY-24)

But there is no mechanism to notify interested consumers (e.g. user alerts, email workers) about the new property in real time. Currently, the only way to discover new listings is via polling the API. Redis Streams provide a pub/sub-with-consumer-groups pattern that enables reliable, at-least-once delivery of events to downstream workers.

## Goals

1. Publish a message to `stream:new_property` after every property upsert in the scrapper-base.
2. Create a base Alert Worker that consumes `stream:new_property` and implements retry/dead-letter semantics.
3. Set up consumer groups with proper stream configuration (MAXLEN, dead-letter).
4. Provide stream management helpers (`StreamManager`) for stream operations.
5. Graceful degradation: if Redis is unavailable, stream operations are silently skipped.

## Non-Goals

- Alert matching against user-defined criteria (STORY-42).
- Email/push notification delivery (STORY-43, STORY-44).
- Consumer group cleanup CronJob (deferred to operations).
- User alerts CRUD endpoints (STORY-42).

## Scope

### Files to create

| File | Purpose |
|------|---------|
| `src/scrapper-base/src/scraper_base/stream_publisher.py` | XADD to `stream:new_property` after upsert |
| `src/real-estate-api/app/services/stream_manager.py` | Redis Stream configuration, helpers, `process_with_retry()` |
| `src/real-estate-api/app/workers/alert_worker.py` | Base Alert Worker consuming `stream:new_property` |

### Files to modify

| File | Change |
|------|--------|
| `src/scrapper-base/src/scraper_base/services.py` | Call `StreamPublisher.publish()` after upsert |
| `src/real-estate-api/app/core/config.py` | Add Redis Stream configuration |
| `src/real-estate-api/app/main.py` | Start/stop Alert Worker in lifespan |

## Acceptance Criteria

1. When a property is upserted (new or update), a message is published to `stream:new_property` in Redis.
2. The Alert Worker connects to `stream:new_property`, creates/joins a consumer group, and reads messages.
3. Successfully processed messages are acknowledged (XACK).
4. Failed messages are retried up to 3 times, then moved to `stream:dead_letter`.
5. All stream `XADD` calls use `MAXLEN` (10,000 for new_property, 1,000 for dead_letter).
6. When Redis is unavailable, publishing is silently skipped (graceful degradation).
7. Worker is started on app startup and stopped on shutdown.

## Stream Architecture

```
scrapper-base upsert_property()
  → StreamPublisher.publish(data)
    → XADD stream:new_property MAXLEN ~10_000

Alert Worker (XREADGROUP from stream:new_property)
  → process_with_retry(stream, group, msg_id, data)
    → success → XACK
    → fail < 3 retries → re-enqueue with _retries+1
    → fail >= 3 retries → XADD stream:dead_letter MAXLEN ~1000 + XACK
```

## Redis Stream Configuration

| Stream | MAXLEN | Consumer Group | Description |
|--------|--------|----------------|-------------|
| `stream:new_property` | ~10,000 | `alert-workers` | Published by scrapper-base on upsert |
| `stream:alerts:pending` | ~5,000 | `email-workers` | Published by Alert Worker (future) |
| `stream:dead_letter` | ~1,000 | — | Failed messages after max retries |

## Retry Policy

- `MAX_RETRIES = 3`
- On failure: re-enqueue with `_retries` counter incremented
- After MAX_RETRIES: move to `stream:dead_letter` with error info
- Dead-letter messages include: `origin_stream`, `msg_id`, `error`, `data`, `timestamp`

## Message Format

```json
{
  "property_id": 1234,
  "portal_source": "otodom",
  "source_id": "abc123",
  "city": "Warszawa",
  "property_type": "apartment",
  "price": 520000,
  "is_new": true,
  "updated_at": "2026-06-25T12:00:00Z"
}
```

## Edge Cases

- Redis connection failure during publish → silent skip (cache invalidator pattern).
- Consumer group already exists → auto-join (stream already has group).
- Stream doesn't exist yet → XADD creates it automatically.
- Worker is stopped mid-processing → pending messages are re-delivered on restart.
- No messages in stream → XREADGROUP blocks with `>` until new messages arrive.
