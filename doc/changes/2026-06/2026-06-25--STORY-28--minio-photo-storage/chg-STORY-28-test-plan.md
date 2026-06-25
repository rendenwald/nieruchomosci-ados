# STORY-28: Test Plan

## Unit Tests

### `tests/test_photo_processor.py` (new file)
| # | Test | Expected |
|---|------|----------|
| TP-1 | `extract_photo_urls` extracts URLs from item data | Returns list of URLs |
| TP-2 | `extract_photo_urls` handles None/empty | Returns empty list |
| TP-3 | `download_photo` downloads bytes from URL | Returns bytes on success |
| TP-4 | `download_photo` returns None on HTTP error | Graceful failure |
| TP-5 | `download_photo` respects timeout | Times out after configured seconds |

### Extend `tests/test_pipeline.py`
| # | Test | Expected |
|---|------|----------|
| TP-6 | `_process_photos` with photo URLs and available MinIO | Photos uploaded, paths returned |
| TP-7 | `_process_photos` with MinIO unavailable | Empty list returned, no crash |
| TP-8 | `_process_photos` enforces MAX_PHOTOS_PER_PROPERTY | Only 20 photos processed |
| TP-9 | `process_item` updates photos field when photos exist | Property has MinIO paths |

## Verification
1. `uv run mypy . --strict` — no errors
2. `uv run ruff check .` — no lint warnings
3. `uv run pytest -v` — all tests pass
