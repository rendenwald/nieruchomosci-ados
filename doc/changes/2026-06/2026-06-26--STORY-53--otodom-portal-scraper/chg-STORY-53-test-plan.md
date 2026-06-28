# Test Plan: STORY-53 — Otodom Portal Scraper

## 1. Test Strategy

| Level | Tool | Scope |
|-------|------|-------|
| Unit (pipeline) | pytest | `OtodomPipeline.item_to_data()` normalization for all field types |
| Unit (spider) | pytest + mock HTTP | Spider parsing from cached HTML fixtures (no live connection) |
| Static analysis | ruff | Code style, imports, naming |
| Type checking | mypy --strict | Type safety for all new modules |

**Approach:**
- Spider tests use pre-recorded HTML snippets stored in `tests/fixtures/` to test parsing logic without live Otodom.pl connections
- Pipeline tests construct `OtodomItem` dicts with known input values and verify normalized output
- No integration/end-to-end tests in this story (requires live Otodom + PostgreSQL)

## 2. Test Environment

- Python ≥3.12, uv-managed virtualenv
- `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- No external services required (DB/MinIO/Redis mocked or absent)

## 3. Test Cases

### 3.1 Pipeline Tests (`tests/test_pipeline.py`)

| TC ID | Description | Input | Expected Output | AC |
|-------|-------------|-------|-----------------|-----|
| TC-P1 | Price normalization — zł suffix | `{"price": "520 000 zł"}` | `{"price": 520000}` | AC-4 |
| TC-P2 | Price normalization — PLN suffix | `{"price": "350000 PLN"}` | `{"price": 350000}` | AC-4 |
| TC-P3 | Price normalization — integer | `{"price": 750000}` | `{"price": 750000}` | AC-4 |
| TC-P4 | Price normalization — invalid | `{"price": "NEGOTIABLE"}` | `{"price": None}` | AC-4 |
| TC-P5 | Area normalization — m² suffix | `{"area": "58,5 m²"}` | `{"area": 58.5}` | AC-5 |
| TC-P6 | Area normalization — m2 suffix | `{"area": "72 m2"}` | `{"area": 72.0}` | AC-5 |
| TC-P7 | Area normalization — no suffix | `{"area": "45"}` | `{"area": 45.0}` | AC-5 |
| TC-P8 | Area normalization — invalid | `{"area": "Ask agent"}` | `{"area": None}` | AC-5 |
| TC-P9 | Photo normalization — list of URL strings | `{"photos": ["http://a.jpg", "http://b.jpg"]}` | `{"photos": ["http://a.jpg", "http://b.jpg"]}` | AC-6 |
| TC-P10 | Photo normalization — mixed valid/invalid | `{"photos": ["http://a.jpg", "", "not-a-url"]}` | `{"photos": ["http://a.jpg"]}` | AC-6 |
| TC-P11 | Photo normalization — empty | `{"photos": None}` | `{"photos": []}` | AC-6 |
| TC-P12 | Price per m² normalization | `{"price_per_m2": "8 500 zł/m²"}` | `{"price_per_m2": 8500}` | AC-4 |
| TC-P13 | Rooms normalization — string | `{"rooms": " 3 "}` | `{"rooms": "3"}` | AC |
| TC-P14 | Rooms normalization — fractional | `{"rooms": "3.5"}` | `{"rooms": "3.5"}` | AC |
| TC-P15 | Floors total normalization | `{"floors_total": "12"}` | `{"floors_total": 12}` | AC |
| TC-P16 | Year built normalization | `{"year_built": "2020"}` | `{"year_built": 2020}` | AC |
| TC-P17 | JSONB extras defaults | `{}` | `{"extras": {}, "localization": {}, "building": {}}` | AC |
| TC-P18 | Portal source set automatically | `{}` | `{"portal_source": "otodom"}` | AC |
| TC-P19 | Plot area normalization | `{"plot_area": "500 m2"}` | `{"plot_area": 500.0}` | AC |

### 3.2 Spider Tests (`tests/test_spider.py`)

| TC ID | Description | Input | Expected Output | AC |
|-------|-------------|-------|-----------------|-----|
| TC-S1 | Parse listing cards from search results | Cached HTML with 3+ listing cards | List of ~3 detail page URLs extracted | AC-1 |
| TC-S2 | Parse pagination next-page URL | Cached HTML with pagination | Next page URL identified | AC-2 |
| TC-S3 | Parse detail page — all fields | Cached detail page HTML | `OtodomItem` with title, price, area, rooms, location, photos | AC-3 |
| TC-S4 | Parse detail page — minimal fields | Cached detail page with minimal data | `OtodomItem` with default/null values for missing fields | AC-3 |
| TC-S5 | Handle search page with no results | Cached empty results HTML | No items yielded, no crash | AC-1 |
| TC-S6 | Spider name is "otodom" | Spider instance | `spider.name == "otodom"` | AC |
| TC-S7 | Allowed domains include otodom.pl | Spider instance | `"otodom.pl" in spider.allowed_domains` | AC |
| TC-S8 | Start URLs include sell listings | Spider instance | Sell listing URL in `start_urls` | AC |

## 4. Traceability Matrix

| AC ID | Test Cases |
|-------|------------|
| AC-1 | TC-S1, TC-S5 |
| AC-2 | TC-S2 |
| AC-3 | TC-S3, TC-S4 |
| AC-4 | TC-P1, TC-P2, TC-P3, TC-P4, TC-P12 |
| AC-5 | TC-P5, TC-P6, TC-P7, TC-P8 |
| AC-6 | TC-P9, TC-P10, TC-P11 |
| AC-7 | TC-P18 (portal_source set for BasePipeline) |
| AC-8 | TC-S1, TC-S2, TC-S3, TC-S4, TC-S5 |
| AC-9 | Static analysis (ruff) |
| AC-10 | Type checking (mypy) |

## 5. Fixtures Required (`tests/conftest.py`)

| Fixture Name | Type | Purpose |
|-------------|------|---------|
| `sample_search_html` | str | Cached search results page with listing cards |
| `sample_detail_html` | str | Cached detail page with full listing data |
| `sample_detail_minimal_html` | str | Cached detail page with minimal data |
| `empty_results_html` | str | Cached search page with no results |
| `sample_item` | dict | Valid `OtodomItem`-like dict for pipeline tests |
| `pipeline` | OtodomPipeline | Configured pipeline instance (no DB init) |
| `spider` | OtodomSpider | Spider instance for tests |

## 6. Quality Gates

- [ ] `ruff check src/otodom-scrapper/` — 0 warnings
- [ ] `mypy --strict src/otodom-scrapper/` — 0 type errors (excluding tests)
- [ ] `pytest tests/ -v --cov=otodom_scrapper --cov-fail-under=80`
