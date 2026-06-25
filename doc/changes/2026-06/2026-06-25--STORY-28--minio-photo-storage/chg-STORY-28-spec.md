# STORY-28: Store scraped photos in MinIO with deduplication

## Problem

When scrapers collect property listings with photo URLs, the photos are stored
as external URLs in the database. These URLs may become stale (host deletes the
photo), and the platform cannot serve them reliably. Photos need to be
downloaded and stored in MinIO with content-based deduplication.

## Goals

- Scraped photos are downloaded and stored in MinIO during scraping
- SHA256-based deduplication prevents storing duplicate photos
- Max 20 photos per property enforced
- Graceful degradation when MinIO or photo URLs are unavailable
- The MinIO storage client already handles SHA256 dedup — integrate it into
  the pipeline's `process_item()` flow

## Scope

| In scope | Out of scope |
|----------|-------------|
| Add `httpx` dependency for async HTTP downloads | Thumbnail generation (STORY-31) |
| Add `_process_photos()` method to `BasePipeline` | Photo serving via CDN (STORY-29) |
| Download photos from URLs in `process_item()` | User-uploaded photos (STORY-30) |
| Upload to MinIO with SHA256 dedup | Orphan photo cleanup (STORY-32) |
| Enforce `MAX_PHOTOS_PER_PROPERTY = 20` | |
| Update property photos field with MinIO paths | |

## Acceptance Criteria

- **AC-1:** `BasePipeline._process_photos()` downloads photo URLs and uploads
  them to MinIO via `MinioStorageClient.upload_photo()`
- **AC-2:** At most `MAX_PHOTOS_PER_PROPERTY` (20) photos are processed per property
- **AC-3:** Photo download failures are logged but do not cause the pipeline to fail
  (non-blocking)
- **AC-4:** MinIO unavailable does not crash the pipeline (graceful degradation)
- **AC-5:** The property's `photos` field is updated with MinIO object paths
- **AC-6:** `httpx` is added as a dependency

## Risks & Dependencies

- Photo download is sequential per property; many photos could slow the pipeline
- Depends on MinIO being configured and available (graceful degradation if not)
- Network failures downloading photos should not block property upsert
