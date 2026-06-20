# AGENTS.md — Constitution for AI (BigPickle)

## Metadata
- **Source:** Real Estate Aggregation Platform v2.1
- **Spec root:** `specs/` (18 modules)
- **Role:** AI coding agent — read this before every task

---

## 1. Core Principles

1. **Always** read the relevant `specs/*.md` module(s) before writing code — start with `specs/000-INDEX.md`.
2. **Do not guess** — if the spec is silent on a detail, stop and ask using the question template below.
3. **Write production code** — type hints on every signature, docstrings on public API, proper error handling.
4. **Tests are first-class** — every function/endpoint gets a pytest unit test. No exceptions.
5. **If the spec says it, do it** — the spec is the source of truth. When in doubt, re-read the spec.

---

## 2. Thinking Process

Before writing a single line of code, run through these steps:

```
Step 1 — ANALYZE
  → Read the spec module(s) for this task
  → Identify inputs, outputs, edge cases
  → Check the "AI Implementation Notes" section at the bottom

Step 2 — PLAN
  → List every file I need to create or modify
  → Check existing code structure via glob/ls
  → Verify the plan against the spec's acceptance criteria

Step 3 — IMPLEMENT
  → Write production code (types, docstrings, error handling)
  → Match the code conventions in sections 4-10 of this file

Step 4 — VERIFY
  → Run the verification commands from the spec's AI Notes
  → Manually check the main flow with curl/browser

Step 5 — REFLECT
  → Does this create tech debt?
  → Should I flag anything to the human?
  → Is there a simpler approach that still meets the spec?
```

---

## 3. Hard Rules (Never Violate)

| Rule | Why |
|------|-----|
| NEVER hardcode secrets, passwords, or API keys — use env vars only | Security |
| NEVER use synchronous DB drivers with FastAPI — use asyncpg / async sessions | Performance |
| NEVER write `print()` — use structured logging via `logging_config.py` | Ops |
| NEVER skip type hints on function signatures | Maintainability |
| NEVER create a file without first checking the repo structure in the spec | Consistency |
| NEVER commit directly to `main` — use feature branches + PR | Git discipline |
| NEVER store files on the filesystem — use MinIO for images, DB for data | Architecture |
| NEVER add `# type: ignore` without a comment explaining why | Quality |
| NEVER write a Gherkin scenario without marking it with its ID (e.g. `MT-5`) | Traceability |

---

## 4. Tech Stack (per spec)

| Layer | Technology | Spec Module |
|-------|------------|-------------|
| Backend | FastAPI + SQLAlchemy 2.0 (async) + Alembic | `080-API.md` |
| Database | PostgreSQL 16 + PostGIS, LIST partitioning on `portal_source` | `070-DATABASE.md` |
| Scraping | Scrapy + Playwright (stealth mode) via `BasePipeline` | `060-SCRAPER-BASE.md` |
| Frontend | SvelteKit + TypeScript + MapLibre GL + paraglide-js | `090-FRONTEND.md`, `100-MAP.md` |
| Cache | Redis 7 (maxmemory 1GB, allkeys-lru, no persist) | `120-CACHING-STORAGE.md` |
| Storage | MinIO (standalone) — SHA256 dedup, thumbnails 400x300 | `120-CACHING-STORAGE.md` |
| Monitoring | Prometheus + Grafana + Loki (7d retention) + Alertmanager | `130-MONITORING-ALERTS.md` |
| CI/CD | GitHub Actions + ArgoCD + Gitea Registry | `140-GITOPS-CICD.md` |
| Infrastructure | k3s single node (local simulation first) | `020-ARCHITECTURE.md` |

### Local Development Ports

| Service | Port |
|---------|------|
| FastAPI | 8000 |
| SvelteKit | 5173 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO Console | 9001 |
| Prometheus | 9090 |
| Grafana | 3000 |

---

## 5. Implementation Patterns

### 5.1 Cache-Aside (Redis)

```python
async def get_properties(params: SearchParams) -> SearchResponse:
    cache_key = f"properties:list:{hash_params(params)}"
    cached = await redis.get(cache_key)
    if cached:
        return SearchResponse.model_validate_json(cached)
    data = await db.query(...)
    await redis.setex(cache_key, 120, data.model_dump_json())
    return data
```

- Try Redis → miss → DB query → write to Redis with TTL → return
- On write: publish to Redis Stream `new_property`, invalidate affected cache keys
- **Graceful degradation:** if Redis is unreachable, skip cache and query DB directly

### 5.2 Scraper (inheritance)

```python
from scraper_base import BasePipeline

class OtodomPipeline(BasePipeline):
    PORTAL_SOURCE = "otodom"

    def item_to_data(self, item: ScrapyItem) -> dict:
        return {
            "title": item["title"],
            "price": int(item["price_raw"]),
            "city": item["city"],
            # ... all fields matching 070-DATABASE.md property schema
        }
```

- Scraper repos depend on `scrapper-base>=1.0.0`
- Metrics are auto-emitted by `BasePipeline` — no manual instrumentation

### 5.3 Deduplication (4 stages)

```
Stage 1 — Blocking:     group by (city + property_type + price ± 20%)
Stage 2 — Heuristics:   filter by area/rooms/floor thresholds
Stage 3 — Fuzzy match:  RapidFuzz on title + address + description (score ≥ 0.85)
Stage 4 — Image hash:   phash comparison (optional, for high-confidence verification)
```

### 5.4 API Patterns (FastAPI)

```python
from fastapi import APIRouter, Depends
from app.schemas import PropertyDetail, ApiError
from app.deps import get_current_user

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])

@router.get("/{id}", response_model=PropertyDetail, responses={404: {"model": ApiError}})
async def get_property(id: int, user: User = Depends(get_current_user)):
    ...
```

- Every endpoint has `response_model=` and error responses documented
- Pagination: `?page=1&limit=20` → `PaginatedResponse<T>` with `meta`
- Auth: JWT Bearer via `Depends(get_current_user)` on protected routes
- Admin routes via `Depends(require_admin)`
- Rate limiting: `slowapi` middleware, Cloudflare later

### 5.5 Database Patterns (SQLAlchemy 2.0)

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Integer

class Property(Base):
    __tablename__ = "properties"
    __table_args__ = {"postgresql_partition_by": "LIST (portal_source)"}

    id: Mapped[int] = mapped_column(primary_key=True)
    portal_source: Mapped[str] = mapped_column(String(50))
    # ...
```

- Use `mapped_column()` declarative style (not `Column()`)
- All queries: `select(Property).where(...)` not raw SQL
- Async: `async with AsyncSession() as session`
- Migrations: `alembic revision --autogenerate -m "description"`

### 5.6 i18n & Currency

```typescript
// Frontend: paraglide-js
import * as m from "$lib/i18n/messages/pl.js";
m.property_price({ price: "520 000", currency: "zł" });

// Currency formatting
new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN" }).format(520000);
```

- Translation files: `src/lib/i18n/messages/{pl,en,de,ua}.json`
- ECB rates fetched daily via CronJob → stored in Redis → served via `/api/v1/exchange-rates`
- Price display: always show original + converted with disclaimer tooltip

### 5.7 Inter-Service Communication (Redis Streams)

```
scrapper-base → XADD stream:new_property → Alert Worker → XREADGROUP
Alert Worker → XADD stream:alerts:pending → Email Worker → XREADGROUP
```

- Each worker is a separate k8s Deployment with its own consumer group
- Dead-letter: failed messages go to `stream:dead_letter` for manual review

---

## 6. Testing Conventions

```
## Structure
tests/
├── conftest.py          ← shared fixtures (DB session, Redis mock, MinIO mock)
├── test_{module}.py     ← one file per module
```

- **One test file per spec module** — e.g. `test_070_database.py`, `test_080_api.py`
- **Framework:** pytest + pytest-asyncio + moto (MinIO mock) + fakeredis
- **Coverage target:** ≥ 80%, no drop from baseline
- **Pattern per function:**

```python
async def test_upsert_property_new(db_session):
    """SB-3: new property should be inserted."""
    ...

async def test_upsert_property_existing(db_session):
    """SB-3: existing property should update last_seen_at."""
    ...

async def test_upsert_property_empty(db_session):
    """Edge case: empty input raises ValueError."""
    with pytest.raises(ValueError):
        ...
```

- Fixtures in `conftest.py` — don't repeat setup in every test file
- DB tests: use a test database or transaction rollback

---

## 7. Git Workflow

| Action | Convention |
|--------|------------|
| Branch name | `feature/{module-id}-{kebab-name}` — e.g. `feature/070-property-model` |
| Commit message | Conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:` |
| PR title | `[#module] Short description` — e.g. `[070] Add Property ORM model` |
| PR description | Reference the spec module: "Implements 070-DATABASE.md" |

---

## 8. When Spec Is Silent — Question Template

If you cannot proceed because a detail is missing, use this exact format:

```
**Question:** [component name] — [one-line summary of what's missing]

**Context:** I'm implementing [feature X] from [spec module]. The spec says
"[quote from spec]" but does not specify [the missing detail].

**Options I see:**
  - A: [option 1] — [pro/con]
  - B: [option 2] — [pro/con]

**My recommendation:** [A/B] because [brief reason].
```

---

## 9. After Coding — Verification Checklist

Before marking a task complete, run through this checklist:

```
Checklist:
[ ] ruff check .                          — no lint warnings
[ ] mypy . --strict                       — no type errors
[ ] pytest tests/ -v --cov=. --cov-fail-under=80  — all tests pass
[ ] npm run build                         — if frontend work
[ ] Manual flow check (curl / browser)    — main scenario works
[ ] No hardcoded values — all config via env vars
[ ] Matches the spec's AI Implementation Notes
[ ] README or AGENTS.md needs updating?   — keep docs current
```

---

## 10. Repository Structure (from spec section 14)

This is the target layout. Generate files in these locations:

| Repository | Purpose | Lead Module |
|------------|---------|-------------|
| `scrapper-base/` | pip package — BasePipeline, dedup, metrics | `060-SCRAPER-BASE.md` |
| `otodom-scrapper/` | Otodom spider | `060-SCRAPER-BASE.md` |
| `nieruchomosci-online-scrapper/` | Nieruchomosci Online spider | `060-SCRAPER-BASE.md` |
| `real-estate-api/` | FastAPI backend | `080-API.md` |
| `real-estate-portal/` | SvelteKit frontend | `090-FRONTEND.md` |
| `infrastructure/` | k8s manifests, ArgoCD apps, monitoring configs | `140-GITOPS-CICD.md` |

---

## 11. Hard Rules — Additions (v2.2)

| Rule | Why |
|------|-----|
| NEVER render raw HTML from external sources — always sanitize with `DOMPurify` | XSS |
| NEVER use `env.value` for credentials in k8s manifests — always `secretKeyRef` | Security |
| NEVER create a CronJob without `concurrencyPolicy: Forbid` | Idempotency |
| NEVER call `REFRESH MATERIALIZED VIEW CONCURRENTLY` before creating a unique index on the view | PostgreSQL error |
| NEVER merge a dedup candidate with fuzzy score < 0.85 — scores 0.80–0.84 go to `deduplication_candidates` | Data quality |
| NEVER upload more than `MAX_PHOTOS_PER_PROPERTY = 20` photos in a single scrape run | Storage protection |
| NEVER write stream messages with `XADD` without `MAXLEN` | Redis memory |

## 12. Verification Checklist — Additions (v2.2)

Add to section 9:

```
[ ] Are changes reversible without a data migration?
[ ] If DB migration — does alembic downgrade -1 succeed on a test DB?
[ ] If new Materialized View — is a unique index created before the first REFRESH CONCURRENTLY?
[ ] If new CronJob — is concurrencyPolicy: Forbid set?
[ ] If new k8s Secret — is it using secretKeyRef (not hardcoded env.value)?
[ ] If rendering external HTML — is DOMPurify sanitizeHtml() wrapping it?
[ ] If XADD to a Redis Stream — is MAXLEN set?
[ ] Is the previous image SHA annotated in the deployment for fast rollback?
```
