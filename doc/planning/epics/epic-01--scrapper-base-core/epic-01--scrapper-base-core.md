# Epic 01: scrapper-base Core

> **Goal:** Provide a reusable Python package (`scrapper-base`) that all portal-specific scrapers depend on. Includes database connectivity, BasePipeline abstraction, metrics emission, and error handling.

## Scope

- Database models and services for PostgreSQL/PostGIS
- `BasePipeline` abstract base class for Scrapy pipelines
- Structured JSON logging
- MinIO storage client
- Prometheus metrics auto-emission

## Success Criteria

- New scraper can be created by subclassing `BasePipeline` and implementing `item_to_data()`
- Concurrent scrapers can write to the DB safely
- Existing records are updated (upsert) not duplicated
- Metrics are auto-emitted without manual instrumentation
- All components are backwards compatible (semver)

## Related Spec Modules

- `specs/060-SCRAPER-BASE.md`
- `specs/070-DATABASE.md`
- `specs/120-CACHING-STORAGE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-1 | Provide `BasePipeline` with DB, logging, metrics | ✅ done |
| STORY-2 | Handle concurrent writes safely | todo |
| STORY-3 | Update `last_seen_at` and changed fields on existing property | ✅ done |
| STORY-4 | Maintain backwards compatibility (semver) | todo |
| STORY-5 | Emit Prometheus metrics automatically | ✅ done |
| STORY-6 | Send alert via Alertmanager on scraper errors | todo |
