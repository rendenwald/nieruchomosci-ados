# AGENTS.md — Constitution for AI Agents

## Metadata
- **Project:** Real Estate Aggregation Platform
- **Repository:** `github.com/rendenwald/nieruchomosci-ados`
- **Role:** AI coding agent — read this before every task
- **Spec root:** `specs/` (18 modules) and `doc/spec/features/` (ADOS feature specs)

---

## 1. Core Principles

1. **Always** read the relevant `specs/*.md` module(s) before writing code — start with `specs/000-INDEX.md`.
2. **Do not guess** — if the spec is silent on a detail, stop and ask using the question template.
3. **Write production code** — type hints on every signature, docstrings on public API, proper error handling.
4. **Tests are first-class** — every function/endpoint gets a pytest unit test. No exceptions.
5. **If the spec says it, do it** — the spec is the source of truth. When in doubt, re-read the spec.
6. **Use ADOS change lifecycle** — follow `doc/guides/change-lifecycle.md` for every change.

---

## 2. Thinking Process

Before writing a single line of code, run through these steps:

```
Step 1 — ANALYZE
  → Read the spec module(s) for this task
  → Check doc/spec/features/ for existing ADOS feature specs
  → Identify inputs, outputs, edge cases
  → Check the "AI Implementation Notes" section at the bottom

Step 2 — PLAN
  → List every file I need to create or modify
  → Check existing code structure via glob/ls
  → Check doc/planning/backlog.md for priority context
  → Verify the plan against the spec's acceptance criteria

Step 3 — IMPLEMENT
  → Write production code (types, docstrings, error handling)
  → Match the code conventions below

Step 4 — VERIFY
  → Run the verification commands from the spec's AI Notes
  → Manually check the main flow

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
| NEVER create a file without first checking the repo structure | Consistency |
| NEVER commit directly to `main` — use feature branches + PR | Git discipline |
| NEVER store files on the filesystem — use MinIO for images, DB for data | Architecture |
| NEVER add `# type: ignore` without a comment explaining why | Quality |
| NEVER write a Gherkin scenario without marking it with its ID (e.g. `SB-3`) | Traceability |
| NEVER render raw HTML from external sources — always sanitize with `DOMPurify` | XSS |
| NEVER use `env.value` for credentials in k8s manifests — always `secretKeyRef` | Security |
| NEVER create a CronJob without `concurrencyPolicy: Forbid` | Idempotency |
| NEVER call `REFRESH MATERIALIZED VIEW CONCURRENTLY` before creating a unique index | PostgreSQL error |
| NEVER merge a dedup candidate with fuzzy score < 0.85 | Data quality |
| NEVER upload more than `MAX_PHOTOS_PER_PROPERTY = 20` photos per scrape run | Storage protection |
| NEVER write stream messages with `XADD` without `MAXLEN` | Redis memory |

---

## 4. Tech Stack

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

## 5. Repository Structure

This is the **main project repo** — code will be organized as follows:

```
/
├── AGENTS.md                    ← This file
├── .ai/                         ← ADOS agent configuration
│   ├── agent/
│   │   ├── pm-instructions.md   ← Project management config
│   │   └── pr-instructions.md   ← PR/MR platform instructions
│   └── local/                   ← Bootstrapper state (git-ignored)
├── doc/                         ← ADOS documentation
│   ├── 00-index.md              ← Documentation index
│   ├── overview/                ← North star, architecture
│   ├── spec/features/           ← ADOS feature specs
│   ├── planning/                ← Local backlog system
│   ├── changes/                 ← Change artifacts
│   ├── decisions/               ← Decision records
│   ├── guides/                  ← ADOS guides
│   └── templates/               ← Document templates
├── specs/                       ← Existing specification modules
│   ├── 000-INDEX.md
│   ├── 010-VISION.md
│   └── ... (18 modules)
├── src/                         ← Source code (to be created)
├── tests/                       ← Test suites (to be created)
├── k8s/                         ← K8s manifests (to be created)
└── .github/                     ← GitHub Actions (to be created)
```

---

## 6. Implementation Patterns

### 6.1 Cache-Aside (Redis)

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

### 6.2 Scraper (inheritance)

```python
from scraper_base import BasePipeline

class OtodomPipeline(BasePipeline):
    PORTAL_SOURCE = "otodom"

    def item_to_data(self, item: ScrapyItem) -> dict:
        return {
            "title": item["title"],
            "price": int(item["price_raw"]),
            "city": item["city"],
        }
```

- Scraper repos depend on `scrapper-base>=1.0.0`
- Metrics are auto-emitted by `BasePipeline` — no manual instrumentation

### 6.3 Deduplication (4 stages)

```
Stage 1 — Blocking:     group by (city + property_type + price ± 20%)
Stage 2 — Heuristics:   filter by area/rooms/floor thresholds
Stage 3 — Fuzzy match:  RapidFuzz on title + address + description (score ≥ 0.85)
Stage 4 — Image hash:   phash comparison (optional, for high-confidence verification)
```

### 6.4 API Patterns (FastAPI)

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

### 6.5 Database Patterns (SQLAlchemy 2.0)

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Integer

class Property(Base):
    __tablename__ = "properties"
    __table_args__ = {"postgresql_partition_by": "LIST (portal_source)"}

    id: Mapped[int] = mapped_column(primary_key=True)
    portal_source: Mapped[str] = mapped_column(String(50))
```

- Use `mapped_column()` declarative style (not `Column()`)
- All queries: `select(Property).where(...)` not raw SQL
- Async: `async with AsyncSession() as session`
- Migrations: `alembic revision --autogenerate -m "description"`

### 6.6 i18n & Currency

```typescript
import * as m from "$lib/i18n/messages/pl.js";
m.property_price({ price: "520 000", currency: "zł" });

new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN" }).format(520000);
```

### 6.7 Inter-Service Communication (Redis Streams)

```
scrapper-base → XADD stream:new_property → Alert Worker → XREADGROUP
Alert Worker → XADD stream:alerts:pending → Email Worker → XREADGROUP
```

- Each worker is a separate k8s Deployment with its own consumer group
- Dead-letter: failed messages go to `stream:dead_letter` for manual review

---

## 7. Testing Conventions

```
tests/
├── conftest.py          ← shared fixtures (DB session, Redis mock, MinIO mock)
├── test_{module}.py     ← one file per module
```

- **One test file per spec module** — e.g. `test_070_database.py`, `test_080_api.py`
- **Framework:** pytest + pytest-asyncio + moto (MinIO mock) + fakeredis
- **Coverage target:** ≥ 80%, no drop from baseline

```python
async def test_upsert_property_new(db_session):
    """SB-3: new property should be inserted."""
    ...

async def test_upsert_property_existing(db_session):
    """SB-3: existing property should update last_seen_at."""
    ...
```

---

## 8. Git Workflow

| Action | Convention |
|--------|------------|
| Branch name | `feature/{module-id}-{kebab-name}` — e.g. `feature/070-property-model` |
| Commit message | Conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:` |
| PR title | `[#module] Short description` — e.g. `[070] Add Property ORM model` |
| PR description | Reference the spec module: "Implements 070-DATABASE.md" |

See `.ai/agent/pr-instructions.md` for PR platform-specific instructions.

---

## 9. Planning & Backlog

This project uses a **local markdown backlog** at `doc/planning/backlog.md`.

- Epics are defined in `doc/planning/epics/`
- Work items use sequential IDs: `STORY-1`, `BUG-1`, `TASK-1`, etc.
- The backlog table is the source of truth for priority and status
- Epic/story files are the source of truth for requirements

See `.ai/agent/pm-instructions.md` for detailed planning conventions.

---

## 10. When Spec Is Silent — Question Template

If you cannot proceed because a detail is missing:

```
**Question:** [component name] — [one-line summary]

**Context:** I'm implementing [feature X] from [spec module]. The spec says
"[quote]" but does not specify [the missing detail].

**Options I see:**
  - A: [option 1] — [pro/con]
  - B: [option 2] — [pro/con]

**My recommendation:** [A/B] because [brief reason].
```

---

## 11. After Coding — Verification Checklist

```
Checklist:
[ ] ruff check .                          — no lint warnings
[ ] mypy . --strict                       — no type errors
[ ] pytest tests/ -v --cov=. --cov-fail-under=80
[ ] npm run build                         — if frontend work
[ ] Manual flow check (curl / browser)
[ ] No hardcoded values — all config via env vars
[ ] Matches the spec's AI Implementation Notes
[ ] AGENTS.md or README needs updating?
[ ] Are changes reversible without a data migration?
[ ] If DB migration — does alembic downgrade -1 succeed on a test DB?
[ ] If new Materialized View — is a unique index created before REFRESH CONCURRENTLY?
[ ] If new CronJob — is concurrencyPolicy: Forbid set?
[ ] If new k8s Secret — is it using secretKeyRef?
[ ] If rendering external HTML — is DOMPurify sanitizeHtml() wrapping it?
[ ] If XADD to a Redis Stream — is MAXLEN set?
```

---

## 12. Reference Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Change Lifecycle | `doc/guides/change-lifecycle.md` | ADOS 10-phase delivery workflow |
| PM Instructions | `.ai/agent/pm-instructions.md` | Project management & backlog rules |
| PR Instructions | `.ai/agent/pr-instructions.md` | PR/MR platform operations |
| Spec Index | `specs/000-INDEX.md` | All 18 spec modules |
| North Star | `doc/overview/01-north-star.md` | Product vision & strategy |
| Architecture | `doc/overview/02-architecture.md` | System architecture overview |
