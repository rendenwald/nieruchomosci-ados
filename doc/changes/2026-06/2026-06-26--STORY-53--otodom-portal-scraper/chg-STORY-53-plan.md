# Implementation Plan: STORY-53 — Otodom Portal Scraper

## Phase 1: Project Scaffold

- [x] Create change folder `doc/changes/2026-06/2026-06-26--STORY-53--otodom-portal-scraper/`
- [x] Create branch `feature/060-otodom-scrapper` from `main`
- [x] Copy `items.py`, `pipelines.py`, `stealth_utils.py` from `src/otodomscraper-old/`
- [x] Fix import in `pipelines.py`: `scraper_base.storage.MAX_PHOTOS_PER_PROPERTY`
- [x] Create `__init__.py` stubs

## Phase 2: Scrapy Project Configuration

### 2.1 `src/otodom-scrapper/pyproject.toml`
- [x] Write pyproject.toml with deps: `scrapper-base`, `scrapy>=2.11`, `scrapy-playwright>=0.0.40`, `playwright-stealth>=1.0.6`
- [x] Set dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

### 2.2 `src/otodom-scrapper/scrapy.cfg`
- [x] Write minimal Scrapy project config (project = otodom_scrapper)

### 2.3 `src/otodom-scrapper/otodom_scrapper/settings.py`
- [x] Set BOT_NAME, SPIDER_MODULES, NEWSPIDER_MODULE
- [x] Configure DOWNLOAD_DELAY=2.0, AUTOTHROTTLE_ENABLED=True, CONCURRENT_REQUESTS_PER_DOMAIN=4
- [x] Configure Playwright: headless=True, download handlers, twisted reactor
- [x] Set ITEM_PIPELINES: `otodom_scrapper.pipelines.OtodomPipeline`: 300
- [x] Set ROBOTSTXT_OBEY=True

### 2.4 `src/otodom-scrapper/otodom_scrapper/middlewares.py`
- [x] Write middleware that applies stealth headers via `setup_page_stealth()`

## Phase 3: OtodomSpider (`spiders/otodom.py`) — MAIN DELIVERABLE

### 3.1 Spider class structure
- [x] `class OtodomSpider(Spider)` with `name = "otodom"`
- [x] `allowed_domains = ["otodom.pl", "www.otodom.pl"]`
- [x] `start_requests` for sell and rent listings (via `start_requests()` generator)
- [x] Custom settings override for Playwright (`PLAYWRIGHT_CONTEXT_NAME`, `PLAYWRIGHT_LAUNCH_OPTIONS`)

### 3.2 Search results parsing
- [x] `parse_search_results()` — parse listing cards, extract detail URLs
- [x] Handle pagination: extract next-page link, yield `scrapy.Request` with Playwright
- [x] Use `scrapy.Request(..., meta={"playwright": True})` for JS rendering

### 3.3 Detail page parsing
- [x] `parse_detail()` — extract all `OtodomItem` fields
- [x] Title: `h1[data-cy="adPageAdTitle"]` CSS
- [x] Price: `strong[data-cy="adPageHeaderPrice"]` CSS → text
- [x] Area: element with aria-label containing "Powierzchnia"
- [x] Rooms: element with aria-label containing "Liczba pokoi"
- [x] Description: `div[data-cy="adPageAdDescription"]` CSS → text
- [x] Photos: gallery image elements (CSS with data-cy attributes)
- [x] Location: breadcrumbs + map data attributes
- [x] Source ID: extract from detail URL pattern (`/UUID/` or `/ID/` segment)
- [x] Property type, auction_type, market_type, condition, heating, floor, year_built from page context

### 3.4 Stealth integration
- [x] Apply `setup_page_stealth()` after page load in both parse methods
- [x] Playwright context created via scrapy-playwright's meta options

## Phase 4: Tests

### 4.1 `tests/conftest.py`
- [x] Create fixtures for spider and pipeline tests
- [x] Create sample HTML fixtures (SAMPLE_SEARCH_HTML, SAMPLE_DETAIL_HTML_FULL, SAMPLE_DETAIL_HTML_MINIMAL, EMPTY_SEARCH_HTML)
- [x] Create `pipeline` fixture (OtodomPipeline instance)
- [x] Create `spider` fixture (OtodomSpider instance)
- [x] Create `make_response()` helper for building mock HtmlResponse objects

### 4.2 `tests/test_pipeline.py`
- [x] TC-P1 through TC-P19: all pipeline normalization test cases
- [x] Test `item_to_data()` with varied inputs (price, area, photos, rooms, floors, year_built, JSONB, defaults)
- [x] Combined full-item integration test

### 4.3 `tests/test_spider.py`
- [x] TC-S1 through TC-S8: spider parsing from mocked HTML
- [x] Test `parse_search_results()` with sample HTML (listing cards, pagination, empty results)
- [x] Test `parse_detail()` with sample detail HTML (full and minimal)
- [x] Test empty results and edge cases
- [x] Test source ID extraction from various URL patterns
- [x] Test property type inference from URL
- [x] Test Playwright page handling (stealth + close)

## Phase 5: Static Analysis & Verification

- [x] Run `ruff check src/otodom-scrapper/` — **ALL CHECKS PASSED** (0 errors)
- [x] Run `mypy --strict src/otodom-scrapper/` — **SUCCESS: no issues found** (0 type errors)
- [x] Run `pytest tests/ -v --cov=otodom_scrapper --cov-fail-under=80` — **75/75 tests PASSED**
- [x] Fix any test failures (7 → 0 after fixes: price empty string, source_id extraction, property_type inference, missing keys)

## Phase 6: Commits

- [x] Commit Phase 2: `feat(otodom): add Scrapy project scaffold and settings`
- [x] Commit Phase 3: `feat(otodom): implement OtodomSpider with Playwright stealth`
- [x] Commit Phase 4: `test(otodom): add spider and pipeline test suite`
- [x] Commit Phase 5: `chore(otodom): fix lint, mypy, and test failures`

---
## Execution Log

| Phase | Status | Evidence |
|-------|--------|----------|
| 1 - Scaffold | ✅ Done (pre-existing) | Branch, folder, init stubs, copied old code |
| 2 - Scrapy Config | ✅ Done | pyproject.toml, scrapy.cfg, settings.py, middlewares.py |
| 3 - OtodomSpider | ✅ Done | `spiders/otodom.py` with all field extraction, stealth, pagination |
| 4 - Tests | ✅ Done | 75 tests: 50 pipeline + 25 spider, all passing |
| 5 - Static Analysis | ✅ Done | ruff=0 errors, mypy=0 errors, pytest=75/75 |
| 6 - Commits | ✅ Done | 4 conventional commits created |
