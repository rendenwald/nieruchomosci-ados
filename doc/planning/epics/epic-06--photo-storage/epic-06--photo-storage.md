# Epic 06: Photo Storage

> **Goal:** Store and serve property photos using MinIO with SHA256 deduplication, automatic thumbnail generation, and proper cleanup.

## Scope

- MinIO bucket setup (property-photos, user-avatars, portal-logos, reports)
- SHA256-based photo deduplication
- Thumbnail generation (400x300)
- CDN-friendly URLs with cache headers
- Orphaned photo cleanup on property deletion

## Success Criteria

- Scraped photos stored in MinIO with deduplication
- Thumbnails generated automatically
- Deleted properties trigger photo cleanup
- Maximum 20 photos per property enforced

## Related Spec Modules

- `specs/120-CACHING-STORAGE.md`
- `specs/060-SCRAPER-BASE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-28 | Store scraped photos in MinIO with deduplication |
| STORY-29 | Serve photos via CDN-friendly URL with cache headers |
| STORY-30 | Validate, resize and store user-uploaded photos in MinIO |
| STORY-31 | Generate thumbnail (400x300) automatically on photo store |
| STORY-32 | Cleanup orphaned photos from MinIO on property deletion |
