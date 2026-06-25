# STORY-28: Implementation Plan

## Files to Modify

### `src/scrapper-base/pyproject.toml`
Add `httpx>=0.27,<1.0` to dependencies.

### `src/scrapper-base/src/scraper_base/pipeline.py`
Add `_process_photos()` method to `BasePipeline`:
1. Extract photo URLs from item data dict
2. Limit to MAX_PHOTOS_PER_PROPERTY (20)
3. Download each photo (async HTTP GET via httpx)
4. Upload to MinIO via `self._minio.upload_photo()`
5. Return list of dicts with MinIO paths

Modify `process_item()` to call `_process_photos()` after upsert and
update the property's photos field.

### `src/scrapper-base/tests/test_photo_processor.py` (new file)
Test photo URL extraction, download, and integration with pipeline.

### `doc/planning/backlog.md`
Mark STORY-28 as done.

## Implementation Details

### Photo processing flow
```python
async def _process_photos(self, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Download photos from URLs in data and upload to MinIO."""
    photo_urls = self._extract_photo_urls(data)
    if not photo_urls:
        return []
    
    photo_urls = photo_urls[:MAX_PHOTOS_PER_PROPERTY]
    results = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in photo_urls:
            try:
                response = await client.get(url)
                response.raise_for_status()
                object_name = await self._minio.upload_photo(response.content)
                if object_name:
                    results.append({
                        "path": object_name,
                        "url": url,
                        "order": len(results) + 1,
                    })
            except Exception:
                self.logger.warning("Photo download failed", url=url, exc_info=True)
    
    return results
```

### Integration in process_item()
After `upsert_property()`, if data has photos and MinIO is available:
1. Call `_process_photos(data)`
2. Append MinIO paths to the property's photos field
3. Only update if photos were actually uploaded
