---
change:
  ref: STORY-53
  type: feat
  status: Proposed
  slug: otodom-portal-scraper
  title: "Otodom Portal Scraper"
  owners: ["rendenwald"]
  service: otodom-scrapper
  labels: ["change", "epic"]
  version_impact: minor
  audience: internal
  security_impact: low
  risk_level: medium
  dependencies:
    internal: ["scrapper-base"]
    external: ["otodom.pl", "playwright", "scrapy-playwright"]
---

# CHANGE SPECIFICATION: Otodom Portal Scraper

> **PURPOSE**: Implement the first portal-specific Scrapy spider for Otodom.pl, reusing `scrapper-base` infrastructure, to scrape real estate listings into the platform.

## 1. SUMMARY

Create a Scrapy scraper package `otodom-scrapper/` with an `OtodomSpider` that navigates Otodom.pl search results, parses listing detail pages, and yields `OtodomItem` instances. The spider uses `scrapy-playwright` with stealth anti-detection measures (`playwright-stealth` + custom JS injections). A pre-existing `OtodomPipeline` (reused from old code) normalizes and persists items via `BasePipeline`. Tests cover spider parsing (from cached HTML fixtures) and pipeline data normalization.

## 2. CONTEXT

### 2.1 Current State Snapshot

The project has `scrapper-base` providing `BasePipeline`, database models (`Property`, `Agency`, `ScraperRun`), MinIO storage, Prometheus metrics, and structured logging. No portal-specific scraper exists yet. Old prototype code exists at `src/otodomscraper-old/` with `items.py`, `pipelines.py`, and `stealth_utils.py` but no spider.

### 2.2 Pain Points / Gaps

- The platform has no real data — all scrapers are unimplemented
- Otodom.pl uses heavy client-side rendering requiring JS execution
- Anti-bot measures require browser automation with stealth techniques
- Old prototype code has a broken import (`MAX_PHOTOS_PER_PROPERTY_APP` doesn't exist) and missing spider

## 3. PROBLEM STATEMENT

Because the platform lacks portal-specific scrapers, no property data can be ingested, resulting in an empty database and no value for end users.

## 4. GOALS

- **G-1**: Scrape apartment/house/plot listings from Otodom.pl sell category
- **G-2**: Parse all fields from listing detail pages into `OtodomItem` (title, price, area, rooms, location, photos, etc.)
- **G-3**: Use Playwright stealth rendering to reliably extract JS-rendered content
- **G-4**: Normalize scraped data via `OtodomPipeline.item_to_data()` (price, area, photos, JSONB fields)
- **G-5**: Persist normalized data through `BasePipeline` DB/Metrics/MinIO pipeline
- **G-6**: Achieve ≥80% test coverage on spider parsing and pipeline normalization

### 4.1 Success Metrics / KPIs

| Metric | Target |
|--------|--------|
| Spider successfully yields items from search results | ≥1 item per 10 listing cards parsed |
| Pipeline normalization handles all field types | 100% of `OtodomItem` fields |
| Test coverage (combined spider + pipeline) | ≥80% |
| `ruff check .` | 0 warnings |
| `mypy --strict` on new package | 0 errors |

### 4.2 Non-Goals

- **NG-1**: Gratka.pl or Nieruchomości Online scrapers (future stories)
- **NG-2**: Rent listings scraping (optional, deferred)
- **NG-3**: Deduplication pipeline configuration (handled by `scrapper-base`)
- **NG-4**: Kubernetes CronJob scheduling (deferred to STORY-40)
- **NG-5**: CI/CD pipeline for the new package (deferred)

## 5. FUNCTIONAL CAPABILITIES

| ID | Capability | Rationale |
|----|------------|-----------|
| F-1 | Search results navigation | Parse listing cards from otodom.pl search page |
| F-2 | Pagination | Follow next-page links to scrape multiple result pages |
| F-3 | Detail page parsing | Extract all property fields from individual listing pages |
| F-4 | Playwright stealth rendering | Bypass anti-bot protection via browser automation + stealth |
| F-5 | Item normalization | Convert raw scraped strings to typed Property schema fields |
| F-6 | Pipeline persistence | Store normalized items via BasePipeline upsert_property() |
| F-7 | Photo URL extraction | Collect gallery photo URLs from detail page |

### 5.1 Capability Details

**F-1 Search results navigation:**
- Spider starts at `https://www.otodom.pl/pl/oferty/sprzedaz/mieszkanie`
- Parses listing card elements for detail page URLs
- Uses Playwright for JS rendering with random user-agent and viewport

**F-3 Detail page parsing:**
- Title: `h1[data-cy="adPageAdTitle"]` selector
- Price: `strong[data-cy="adPageHeaderPrice"]` selector
- Area: element with `aria-label` containing "Powierzchnia"
- Rooms: element with `aria-label` containing "Liczba pokoi"
- Description: `div[data-cy="adPageAdDescription"]`
- Photos: `img[data-cy="adPageGalleryImage"]` or gallery data attributes
- Location: breadcrumbs + map data attributes

## 6. SCOPE & BOUNDARIES

### 6.1 In Scope

- `src/otodom-scrapper/` — complete Scrapy project package
- `OtodomSpider` — crawl sell listings, parse detail pages
- `OtodomPipeline.item_to_data()` — normalize and persist
- Test suite: spider parsing (fixture-based), pipeline normalization

### 6.2 Out of Scope

- [OUT] Rent listings — spider can be extended later
- [OUT] Otodom API integration (public API may exist but we use scraping)
- [OUT] Production deployment (CronJob, Dockerfile, Helm chart)
- [OUT] Continuous data quality monitoring

## 7. INTERFACES & INTEGRATION CONTRACTS

### 7.1 Data Model Impact

| ID | Element | Description |
|----|---------|-------------|
| DM-1 | `OtodomItem` | Scrapy Item matching `Property` model fields (73 lines, all fields) |
| DM-2 | `OtodomPipeline` | Subclass of `BasePipeline` with `item_to_data()` mapping |

### 7.2 External Integrations

- **Otodom.pl**: HTTP target — no API key required
- **scrapper-base**: Local pip dependency (`../scrapper-base`)
- **Playwright**: Browser automation for JS rendering

## 8. NON-FUNCTIONAL REQUIREMENTS

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Download delay between requests | ≥2.0 seconds (DOWNLOAD_DELAY) |
| NFR-2 | Concurrent requests per domain | ≤4 (CONCURRENT_REQUESTS_PER_DOMAIN) |
| NFR-3 | Autothrottle enabled | True |
| NFR-4 | Playwright headless mode | True |
| NFR-5 | `robots.txt` obeyed | True |

## 9. RISKS & MITIGATIONS

| ID | Risk | Impact | Probability | Mitigation | Residual Risk |
|----|------|--------|-------------|------------|---------------|
| RSK-1 | Otodom HTML structure changes | H | M | Use generic selectors + data attributes; document fingerprints | M |
| RSK-2 | Playwright browser binary missing | H | L | Document setup: `playwright install chromium` | L |
| RSK-3 | Otodom anti-bot blocks headless browser | M | M | Use `playwright-stealth` + custom JS + random UA/viewport | M |
| RSK-4 | Slow page load causes timeout | L | M | Configure `PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT` | L |

## 10. ACCEPTANCE CRITERIA

| ID | Criterion | Linked |
|----|-----------|--------|
| AC-1 | **Given** an Otodom search results page, **when** the spider processes it, **then** listing card URLs are extracted and scheduled for detail parsing | F-1 |
| AC-2 | **Given** a search results page with pagination, **when** the spider reaches the bottom, **then** the next page URL is extracted and enqueued | F-2 |
| AC-3 | **Given** a listing detail page, **when** the spider parses it, **then** title, price, area, rooms, location, and photos are extracted into an `OtodomItem` | F-3 |
| AC-4 | **Given** a raw price string like "520 000 zł", **when** `item_to_data()` processes it, **then** the result is `int(520000)` | F-5 |
| AC-5 | **Given** a raw area string like "58,5 m²", **when** `item_to_data()` processes it, **then** the result is `float(58.5)` | F-5 |
| AC-6 | **Given** a raw photos field containing URL strings, **when** `item_to_data()` processes it, **then** the result is a list of valid HTTP URLs (max 20) | F-5 |
| AC-7 | **Given** an `OtodomItem` with valid fields, **when** processed by `OtodomPipeline`, **then** it is persisted via `BasePipeline.upsert_property()` | F-6 |
| AC-8 | **Given** cached HTML fixtures, **when** test runs, **then** spider parsing is verified for search results and detail pages | F-1, F-3 |
| AC-9 | **Given** the package directory, **when** `ruff check src/otodom-scrapper/` runs, **then** 0 warnings | NFR |
| AC-10 | **Given** the package directory, **when** `mypy --strict src/otodom-scrapper/` runs, **then** 0 type errors (excluding tests) | NFR |

## 11. AFFECTED COMPONENTS

| Component | Impact |
|-----------|--------|
| `src/otodom-scrapper/` | **New** — entire Scrapy project |
| `src/scrapper-base/` | **Unchanged** — consumed as dependency |

## 12. ROLLOUT & CHANGE MANAGEMENT

- Branch: `feature/060-otodom-scrapper` from `main`
- PR merge strategy: Squash
- Verification: `scrapy crawl otodom -s CLOSESPIDER_PAGECOUNT=5` dry-run

## 13. DATA MIGRATION / SEEDING

N/A — no database schema changes.

## 14. GLOSSARY

| Term | Definition |
|------|------------|
| Otodom.pl | Largest Polish real estate classifieds portal |
| Stealth mode | Anti-detection techniques for headless browsers |
| `BasePipeline` | Abstract Scrapy pipeline from `scrapper-base` |
| `OtodomItem` | Scrapy Item with all property fields |

## 15. DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-26 | @pm | Initial specification |
