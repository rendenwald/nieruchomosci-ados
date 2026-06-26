# Implementation Plan: STORY-53 — Otodom Portal Scraper

## Phase 1: Project Scaffold

- [x] Create change folder `doc/changes/2026-06/2026-06-26--STORY-53--otodom-portal-scraper/`
- [x] Create branch `feature/060-otodom-scrapper` from `main`
- [x] Copy `items.py`, `pipelines.py`, `stealth_utils.py` from `src/otodomscraper-old/`
- [x] Fix import in `pipelines.py`: `scraper_base.storage.MAX_PHOTOS_PER_PROPERTY`
- [x] Create `__init__.py` stubs

## Phase 2: Scrapy Project Configuration

### 2.1 `src/otodom-scrapper/pyproject.toml`
- [ ] Write pyproject.toml with deps: `scrapper-base`, `scrapy>=2.11`, `scrapy-playwright>=0.0.40`, `playwright-stealth>=1.0.6`
- [ ] Set dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

### 2.2 `src/otodom-scrapper/scrapy.cfg`
- [ ] Write minimal Scrapy project config (project = otodom_scrapper)

### 2.3 `src/otodom-scrapper/otodom_scrapper/settings.py`
- [ ] Set BOT_NAME, SPIDER_MODULES, NEWSPIDER_MODULE
- [ ] Configure DOWNLOAD_DELAY=2.0, AUTOTHROTTLE_ENABLED=True, CONCURRENT_REQUESTS_PER_DOMAIN=4
- [ ] Configure Playwright: headless=True, download handlers, twisted reactor
- [ ] Set ITEM_PIPELINES: `otodom_scrapper.pipelines.OtodomPipeline`: 300
- [ ] Set ROBOTSTXT_OBEY=True

### 2.4 `src/otodom-scrapper/otodom_scrapper/middlewares.py`
- [ ] Write placeholder middleware module (empty, Scrapy requires it)

## Phase 3: OtodomSpider (`spiders/otodom.py`) — MAIN DELIVERABLE

### 3.1 Spider class structure
- [ ] `class OtodomSpider(Spider)` with `name = "otodom"`
- [ ] `allowed_domains = ["otodom.pl", "www.otodom.pl"]`
- [ ] `start_urls` for sell listings
- [ ] Custom settings override for Playwright (`PLAYWRIGHT_CONTEXT_NAME`, `PLAYWRIGHT_LAUNCH_OPTIONS`)

### 3.2 Search results parsing
- [ ] `parse_search_results()` — parse listing cards, extract detail URLs
- [ ] Handle pagination: extract next-page link, yield `scrapy.Request` with Playwright
- [ ] Use `scrapy.Request(..., meta={"playwright": True})` for JS rendering

### 3.3 Detail page parsing
- [ ] `parse_detail()` — extract all `OtodomItem` fields
- [ ] Title: `h1[data-cy="adPageAdTitle"]` CSS
- [ ] Price: `strong[data-cy="adPageHeaderPrice"]` CSS → text
- [ ] Area: element with aria-label containing "Powierzchnia"
- [ ] Rooms: element with aria-label containing "Liczba pokoi"
- [ ] Description: `div[data-cy="adPageAdDescription"]` CSS → text
- [ ] Photos: gallery image elements (CSS selectors for data attributes)
- [ ] Location: breadcrumbs + map data attributes
- [ ] Source ID: extract from detail URL pattern (`/ID/` segment)
- [ ] Property type, auction_type, market_type from page context

### 3.4 Stealth integration
- [ ] Use `create_stealth_context()` from `stealth_utils` for Playwright context creation
- [ ] Apply `simulate_human_behavior()` after page load
- [ ] Set up stealth via `@playwright_page_init` handler

## Phase 4: Tests

### 4.1 `tests/conftest.py`
- [ ] Create `pytest_configure()` / fixtures for spider and pipeline tests
- [ ] Create sample HTML fixtures (inline or as string constants)
- [ ] Create `pipeline` fixture (OtodomPipeline instance)
- [ ] Create `spider` fixture (OtodomSpider instance)

### 4.2 `tests/test_pipeline.py`
- [ ] TC-P1 through TC-P19: all pipeline normalization test cases
- [ ] Test `item_to_data()` with varied inputs

### 4.3 `tests/test_spider.py`
- [ ] TC-S1 through TC-S8: spider parsing from mocked HTML
- [ ] Test `parse_search_results()` with sample HTML
- [ ] Test `parse_detail()` with sample detail HTML
- [ ] Test empty results and edge cases

## Phase 5: Static Analysis & Verification

- [ ] Run `ruff check src/otodom-scrapper/` — fix all warnings
- [ ] Run `mypy --strict src/otodom-scrapper/` — fix all type errors (exclude tests)
- [ ] Run `pytest tests/ -v --cov=otodom_scrapper --cov-fail-under=80`
- [ ] Fix any test failures

## Phase 6: Commits

- [ ] Commit Phase 2: "feat(otodom): add Scrapy project scaffold and settings"
- [ ] Commit Phase 3: "feat(otodom): implement OtodomSpider with Playwright stealth"
- [ ] Commit Phase 4: "test(otodom): add spider and pipeline test suite"
- [ ] Commit Phase 5: "chore(otodom): fix lint and type errors"
