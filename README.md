# Real Estate Aggregation Platform

**Self-hosted, open-source platform** that scrapes Polish real estate portals (Otodom, Gratka, Nieruchomości Online), deduplicates listings, and provides a unified search experience with an interactive map.

| Attribute | Value |
|-----------|-------|
| **Repository** | [github.com/rendenwald/nieruchomosci-ados](https://github.com/rendenwald/nieruchomosci-ados) |
| **Language** | Python 3.12+, TypeScript (SvelteKit) |
| **License** | MIT |
| **Status** | Active development |

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Components](#components)
  - [scrapper-base](#1-scrapper-base)
  - [real-estate-api](#2-real-estate-api)
  - [Portal Scrapers](#3-portal-scrapers)
  - [Frontend (SvelteKit)](#4-frontend-sveltekit)
- [Configuration](#configuration)
- [Docker & Docker Compose](#docker--docker-compose)
- [CI/CD Pipeline](#cicd-pipeline)
- [Monitoring & Alerting](#monitoring--alerting)
- [Storage Layer](#storage-layer)
- [Development Guide](#development-guide)
- [Testing](#testing)
- [Deployment](#deployment)
- [Glossary](#glossary)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub Actions CI/CD                      │
│   Ruff → Mypy → Pytest → Docker Build → Push to GHCR → ArgoCD  │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Otodom      │    │ Nieruchom.   │    │  Gratka      │
│  Scraper     │    │ Online Scrp. │    │  Scraper     │
│  (CronJob)   │    │ (CronJob)    │    │  (CronJob)   │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  scrapper-base │  ← shared library (BasePipeline, metrics, logging)
                    │  (pip package) │
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
       ┌──────▼─────┐ ┌────▼────┐ ┌──────▼──────┐
       │ PostgreSQL │ │  Redis  │ │    MinIO    │
       │  + PostGIS │ │  Cache  │ │  (Photos)   │
       └────────────┘ └─────────┘ └─────────────┘
              │
       ┌──────▼──────┐
       │ FastAPI API │
       │ real-estate │
       │ -api        │
       └──────┬──────┘
              │
       ┌──────▼──────┐
       │  SvelteKit  │
       │  Frontend   │
       │  + MapLibre │
       └─────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Prometheus + Grafana + Loki                  │
│                       Alertmanager (alerts)                      │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Portal Scrapers** (Otodom, Nieruchomosci Online, Gratka) run on a schedule via Kubernetes CronJobs
2. Each scraper uses `scrapper-base` (shared library) for DB writes, logging, metrics, and photo storage
3. Properties are upserted atomically into **PostgreSQL** with PostGIS for geospatial queries
4. Photos are uploaded to **MinIO** with SHA256 deduplication
5. On upsert, cache invalidation publishes to **Redis Streams**
6. **FastAPI** serves the REST API with Redis cache-aside pattern
7. **SvelteKit** frontend renders the interactive map with MapLibre GL
8. **Prometheus** scrapes metrics from all services; **Alertmanager** sends alerts
9. **ArgoCD** automates deployments when new Docker images are pushed to GHCR

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- PostgreSQL 16 + PostGIS (or use Docker Compose)

### 1. Clone & Setup

```bash
git clone https://github.com/rendenwald/nieruchomosci-ados.git
cd nieruchomosci-ados

# Copy environment configuration
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start Infrastructure (Docker Compose)

```bash
docker compose up -d postgres redis minio pushgateway prometheus alertmanager
```

### 3. Setup Python Environments

```bash
# scrapper-base shared library
uv sync --directory src/scrapper-base --extra dev

# FastAPI API
uv sync --directory src/real-estate-api --extra dev

# Otodom scraper
uv sync --directory src/otodom-scrapper --extra dev
```

### 4. Run Database Migrations

```bash
uv run --directory src/scrapper-base alembic upgrade head
```

### 5. Start the API

```bash
uv run --directory src/real-estate-api uvicorn app.main:app --reload --port 8000
```

### 6. Verify

```bash
curl http://localhost:8000/health
# {"status": "ok", "redis": "ok"}

curl http://localhost:8000/ready
# {"ready": true, "redis": "ok"}
```

---

## Project Structure

```
├── AGENTS.md                    ← Agent constitution (AI development rules)
├── README.md                    ← This file
├── .env.example                 ← Environment variable template
├── docker-compose.yml           ← Local development services
├── Dockerfile.*                 ← Multi-stage Docker builds
│
├── src/
│   ├── scrapper-base/           ← Shared scraper infrastructure (pip package)
│   │   ├── pyproject.toml
│   │   └── src/scraper_base/
│   │       ├── models.py        ← SQLAlchemy ORM models
│   │       ├── services.py      ← Property/Agency upsert logic
│   │       ├── pipeline.py      ← BasePipeline ABC for scrapers
│   │       ├── metrics.py       ← Prometheus metrics
│   │       ├── storage.py       ← MinIO photo storage client
│   │       ├── logging_config.py
│   │       ├── cache_invalidator.py  ← Redis cache invalidation
│   │       └── ...              ← Deduplication, DB utils, etc.
│   │
│   ├── real-estate-api/         ← FastAPI REST API
│   │   ├── pyproject.toml
│   │   └── app/
│   │       ├── main.py          ← FastAPI application factory
│   │       ├── core/config.py   ← pydantic-settings
│   │       ├── core/metrics.py  ← API-level Prometheus metrics
│   │       ├── routers/         ← API endpoints
│   │       │   ├── properties.py
│   │       │   ├── health.py
│   │       │   └── readiness.py
│   │       └── services/        ← Business logic
│   │           ├── cache_service.py   ← Redis cache-aside
│   │           ├── redis_client.py    ← Connection pool + health
│   │           └── property_service.py
│   │
│   ├── otodom-scrapper/         ← Otodom.pl portal scraper
│   │   ├── pyproject.toml
│   │   └── otodom_scrapper/
│   │       ├── items.py         ← OtodomItem (30+ fields)
│   │       ├── pipelines.py     ← OtodomPipeline (inherits BasePipeline)
│   │       ├── spiders/otodom.py← OtodomSpider (Playwright + stealth)
│   │       ├── stealth_utils.py ← Anti-detection utilities
│   │       └── settings.py      ← Scrapy configuration
│   │
│   └── frontend/                ← SvelteKit frontend (planned)
│       └── ...
│
├── specs/                       ← Canonical specification modules
│   ├── 000-INDEX.md
│   ├── 010-VISION.md
│   ├── 020-ARCHITECTURE.md
│   ├── ...
│   └── 180-ROADMAP.md
│
├── doc/
│   ├── overview/                ← Architecture, north star, caching docs
│   ├── decisions/               ← Architecture Decision Records (ADRs)
│   ├── planning/                ← Backlog, epics, work items
│   └── changes/                 ← Change lifecycle artifacts
│
├── docker/
│   ├── prometheus/              ← Prometheus config + alert rules
│   │   ├── prometheus.yml
│   │   └── alert-rules.yml
│   └── alertmanager/            ← Alertmanager config
│       └── alertmanager.yml
│
└── k8s/                         ← Kubernetes manifests (planned)
    ├── scrapers/
    ├── app/
    ├── storage/
    └── monitoring/
```

---

## Components

### 1. scrapper-base

**Location:** `src/scrapper-base/`

Shared library used by all portal scrapers. Provides:

| Module | Purpose |
|--------|---------|
| `BasePipeline` | ABC with DB write, logging, metrics, MinIO photo storage |
| `PropertyService.upsert_property()` | Atomic upsert with concurrent-write safety |
| `models.py` | SQLAlchemy ORM (Property, Agency, ScraperRun) |
| `metrics.py` | Prometheus counters, histograms, Pushgateway helper |
| `storage.py` | MinIO client with SHA256 dedup, async wrapper |
| `cache_invalidator.py` | Redis cache key invalidation on upsert |
| `deduplication/` | 4-stage dedup pipeline (blocking, heuristics, fuzzy, phash) |

**Usage in a portal scraper:**

```python
from scraper_base import BasePipeline

class MyPortalPipeline(BasePipeline):
    PORTAL_SOURCE = "my_portal"

    def item_to_data(self, item):
        return {
            "title": item["title"],
            "price": int(item["price_raw"]),
            "city": item["city"],
            # ... map to normalized schema
        }
```

### 2. real-estate-api

**Location:** `src/real-estate-api/`

FastAPI application with Redis cache-aside layer.

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `GET /health` | Service health (Redis status) | None |
| `GET /ready` | Readiness probe (HTTP 503 if degraded) | None |
| `GET /api/v1/properties` | Search properties (9 filters) | Redis, TTL 120s |
| `GET /api/v1/properties/{id}` | Single property detail | Redis, TTL 300s (planned) |
| `GET /api/v1/cities` | Cities with offer counts | Redis, TTL 3600s |
| `GET /metrics` | Prometheus metrics | None |

**Cache invalidation:** When a new property is upserted by a scraper:
- On **insert** (`is_new=True`): SCAN + DEL all `properties:list:v1:*` keys + DEL `cities:list`
- On **update** (`is_new=False`): DEL `properties:detail:{id}` only

**Graceful degradation:** When Redis is unavailable:
- Falls back to direct DB query (`miss (fallback)`)
- Background recovery worker pings Redis every 30s
- `GET /ready` returns 503 after startup grace period

### 3. Portal Scrapers

Each portal has its own Scrapy project inheriting from `scrapper-base`.

#### Otodom Scraper

**Location:** `src/otodom-scrapper/`

| Component | Description |
|-----------|-------------|
| **Spider** | `OtodomSpider` — crawls search results + detail pages |
| **Pipeline** | `OtodomPipeline` — field normalization, inherits `BasePipeline` |
| **Stealth** | Playwright anti-detection (random UAs, viewport, JS injection) |
| **Items** | `OtodomItem` — 30+ fields matching the Property schema |

**Running the spider:**

```bash
cd src/otodom-scrapper

# Scrape sell listings
uv run scrapy crawl otodom -a category=sprzedaz

# Scrape rent listings
uv run scrapy crawl otodom -a category=wynajem
```

**Updating test fixtures:**

Save a real otodom.pl search results page to `tests/otodom-search-results/`:

```bash
curl "https://www.otodom.pl/pl/oferty/sprzedaz/mieszkanie" \
  -o src/otodom-scrapper/tests/otodom-search-results/search-results-with-photos.html
```

#### Other Scrapers (planned)

- `src/nieruchomosci-online-scrapper/` — Nieruchomosci Online portal
- `src/gratka-scrapper/` — Gratka portal

### 4. Frontend (SvelteKit)

**Location:** `src/frontend/` (planned)

- MapLibre GL with clustering and polygon filtering
- Multi-language UI (PL/EN/DE/UA) via paraglide-js
- Multi-currency support (PLN/EUR/USD/GBP/UAH) via daily ECB rates
- User alerts with email and push notifications

---

## Configuration

All credentials are configured via environment variables (never hardcoded).

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/realestate` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `REDIS_ENABLED` | `true` | Set to `false` to skip Redis entirely |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO server endpoint |
| `MINIO_ACCESS_KEY` | — | MinIO access key |
| `MINIO_SECRET_KEY` | — | MinIO secret key |
| `MINIO_BUCKET` | `property-photos` | MinIO bucket name |

### Cache

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TTL_SECONDS` | `120` | Default cache TTL (seconds) |
| `CACHE_KEY_PREFIX` | `properties:list:v1` | Cache key prefix for properties |
| `REDIS_POOL_SIZE` | `10` | Max Redis connections |
| `REDIS_TIMEOUT_SECONDS` | `2` | Redis operation timeout |
| `REDIS_HEALTH_CHECK_INTERVAL` | `30` | Seconds between health checks |
| `REDIS_HEALTH_CHECK_FAILURE_THRESHOLD` | `3` | Consecutive failures before degraded |
| `REDIS_STARTUP_GRACE_PERIOD` | `30` | Seconds before /ready returns 503 |

### API

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PREFIX` | `/api/v1` | API base path |
| `PROPERTIES_MAX_LIMIT` | `100` | Max items per page |
| `PROPERTIES_DEFAULT_LIMIT` | `20` | Default items per page |
| `METRICS_ENABLED` | `true` | Enable Prometheus metrics |

### Alerting

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERTMANAGER_URL` | `http://localhost:9093` | Alertmanager webhook URL |
| `ERROR_RATE_THRESHOLD` | `5` | Error rate % before alerting |

---

## Docker & Docker Compose

### Services

```yaml
services:
  postgres:     # PostgreSQL 16 + PostGIS (port 5432)
  redis:        # Redis 7 (port 6379), maxmemory 1GB, allkeys-lru
  minio:        # MinIO standalone (ports 9000, 9001)
  pushgateway:  # Prometheus Pushgateway (port 9091)
  prometheus:   # Prometheus (port 9090)
  alertmanager: # Alertmanager (port 9093)
  real-estate-api: # FastAPI app (port 8000)
```

### Start all services

```bash
docker compose up -d
```

### Build & push individual services

```bash
# Build the API
docker build -f src/real-estate-api/Dockerfile -t real-estate-api:latest .

# Build a scraper
docker build -f src/otodom-scrapper/Dockerfile -t otodom-scrapper:latest .
```

---

## CI/CD Pipeline

The pipeline is defined in `.github/workflows/ci.yml`.

### Stages

```
Push to main (or PR)
    │
    ▼
┌─────────────────────────┐
│  Quality Gate (matrix)  │
│  ┌───────────────────┐  │
│  │ ruff check .      │  │
│  │ mypy --strict .   │  │
│  │ pytest -v --cov   │  │
│  └───────────────────┘  │
└──────────┬──────────────┘
           │ (on main only)
           ▼
┌─────────────────────────┐
│  Build & Push to GHCR   │
│  ghcr.io/rendenwald/    │
│  nieruchomosci-ados:    │
│  {sha}                  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  ArgoCD auto-sync       │
│  (detects new image,    │
│   rolls out to k3s)     │
└─────────────────────────┘
```

### Key Features

- **Parallel matrix**: Runs ruff, mypy, pytest on both `real-estate-api` and `scrapper-base` simultaneously
- **Docker build**: Multi-stage builds with security scan (Trivy)
- **GHCR push**: Uses `GITHUB_TOKEN` for authentication (no separate credentials)
- **Auto-rollback**: If deployment fails, ArgoCD reverts to the previous version
- **Preview deploy**: PRs get a full test suite run

---

## Monitoring & Alerting

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cache_hits_total` | Counter | endpoint, cache_key_prefix | Cache hit count |
| `cache_misses_total` | Counter | endpoint, cache_key_prefix | Cache miss count |
| `cache_errors_total` | Counter | endpoint, operation, error_type | Redis errors |
| `cache_operation_duration_seconds` | Histogram | endpoint, operation | Redis op latency |
| `redis_degraded` | Gauge | endpoint | 1 if Redis degraded, 0 otherwise |
| `scraper_last_run_timestamp` | Gauge | portal | Last scraper run timestamp |
| `listings_scraped_total` | Counter | portal | Properties scraped |
| `scrape_errors_total` | Counter | portal, error_type | Scrape errors |
| `cache_invalidation_total` | Counter | operation, status | Cache invalidations |

### Grafana Dashboards (planned)

- **Scrapers**: Listings scraped, errors, duration per portal
- **API**: Request rate, latency p50/p95/p99, cache hit ratio
- **System**: Redis memory, PostgreSQL connections, MinIO usage
- **Combined**: Single-pane view with all metrics

### Alertmanager Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| `RedisDegraded` | `redis_degraded == 1` for > 5m | warning |
| `ScraperErrorRate` | Error rate > 5% | critical |
| `HighMemoryUsage` | Redis memory > 90% | warning |
| `ContainerCrash` | Container restart > 3 in 1m | critical |

### Logging

- All services use **structlog** structured JSON logging
- **Loki** collects and stores logs (7-day retention)
- Log format: `{"event": "upsert_complete", "property_id": 123, "portal": "otodom"}`

---

## Storage Layer

### PostgreSQL 16 + PostGIS

- **Schema**: Properties, Agencies, ScraperRuns, DeduplicationCandidates
- **Partitioning**: LIST partitioned by `portal_source` (otodom, gratka, nieruchomosci-online)
- **PostGIS**: Geospatial queries for map markers and polygon filtering
- **Async**: SQLAlchemy 2.0 async with asyncpg driver

### Redis 7

- **Purpose**: API response cache (cache-aside pattern)
- **Memory**: maxmemory 1GB, allkeys-lru eviction
- **Persistence**: None (cache only, data loss is acceptable)
- **Streams**: Real-time alert delivery (`stream:new_property`, `stream:alerts:pending`)
- **Key format**:
  - `properties:list:v1:{sha256(params)}` — Search results (TTL 120s)
  - `properties:detail:{id}` — Property detail (TTL 300s)
  - `cities:list` — City list (TTL 3600s)

### MinIO

- **Purpose**: Photo storage with SHA256 deduplication
- **Bucket**: `property-photos`
- **Thumbnails**: 400x300px auto-generated (planned)
- **Max photos**: 20 per property (`MAX_PHOTOS_PER_PROPERTY`)
- **Access**: Presigned URLs with cache headers (planned)

---

## Development Guide

### Prerequisites

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Rust (for Playwright)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install Playwright browsers
uv run --directory src/otodom-scrapper playwright install chromium
```

### Python Environment

```bash
# Use uv for all Python package management
uv sync --directory src/scrapper-base --extra dev
uv sync --directory src/real-estate-api --extra dev
uv sync --directory src/otodom-scrapper --extra dev
```

### Code Quality

```bash
# Lint (ruff)
uv run --directory src/scrapper-base ruff check .
uv run --directory src/real-estate-api ruff check .

# Type checking (mypy strict)
uv run --directory src/scrapper-base mypy src/scrapper-base/
uv run --directory src/real-estate-api mypy src/real-estate-api/

# Formatting
uv run --directory src/scrapper-base ruff format .
```

### Database Migrations

```bash
# Create a new migration
uv run --directory src/scrapper-base alembic revision --autogenerate -m "description"

# Apply migrations
uv run --directory src/scrapper-base alembic upgrade head

# Rollback
uv run --directory src/scrapper-base alembic downgrade -1
```

---

## Testing

### Run All Tests

```bash
# scrapper-base (98 tests)
uv run --directory src/scrapper-base pytest -v

# real-estate-api (59 tests)
uv run --directory src/real-estate-api pytest -v

# otodom-scrapper (84 tests)
uv run --directory src/otodom-scrapper pytest -v

# With coverage
uv run --directory src/real-estate-api pytest --cov=app --cov-report=term
```

### Test Structure

```
tests/
├── conftest.py              ← Shared fixtures (DB, Redis mock, MinIO mock)
├── test_*.py                ← One file per module/feature
├── otodom-search-results/   ← Saved HTML fixtures for spider tests
│   └── search-results-with-photos.html
```

### Test Fixtures

- **Redis**: `fakeredis[lua]` for unit tests (no real Redis in CI)
- **Database**: In-memory SQLite with geoalchemy2 DDL suppression
- **MinIO**: `MockMinioClient` (no real MinIO needed)
- **HTTP**: Inline HTML strings or saved HTML files in `tests/otodom-search-results/`
- **Spider**: `HtmlResponse` with `make_response()` helper — no network requests

---

## Deployment

### Local (Docker Compose)

```bash
# Full stack
docker compose up -d

# Scale API replicas
docker compose up -d --scale real-estate-api=3
```

### Kubernetes (k3s)

Manifests are under `k8s/` (being built):

```bash
# Apply namespaces
kubectl apply -f k8s/namespaces/

# Deploy storage
kubectl apply -f k8s/storage/

# Deploy scrapers
kubectl apply -f k8s/scrapers/

# Deploy API
kubectl apply -f k8s/app/

# Deploy monitoring
kubectl apply -f k8s/monitoring/
```

### GitOps with ArgoCD

ArgoCD watches the `k8s/` directory in the Git repository and auto-syncs:

1. CI builds Docker image → pushes to `ghcr.io/rendenwald/nieruchomosci-ados:{sha}`
2. CI updates the k8s manifest with the new image tag
3. ArgoCD detects the diff and applies the change
4. If the deployment fails, ArgoCD auto-rolls back to the previous version

```bash
# Manual rollback if needed
argocd app rollback <app-name> --revision <previous-revision>
kubectl set image deployment/real-estate-api \
  api=ghcr.io/rendenwald/real-estate-api:<previous-sha>
```

---

## Glossary

| Term | Definition |
|------|------------|
| **scrapper-base** | Shared Python library with `BasePipeline`, DB models, metrics, logging |
| **BasePipeline** | Scrapy pipeline base class — handles DB upsert, metrics, photos |
| **Portal Scraper** | A Scrapy project for a specific portal (Otodom, Gratka, etc.) |
| **ADR** | Architecture Decision Record — documents architectural choices |
| **GHCR** | GitHub Container Registry — stores Docker images |
| **ArgoCD** | GitOps deployment tool — auto-syncs k8s from Git |
| **Cache-aside** | Read pattern: check cache → miss → query DB → write cache |
| **Cache invalidation** | Deleting stale cache keys when data changes |
| **PostGIS** | Spatial extension for PostgreSQL (geographic queries) |
| **structlog** | Structured JSON logging library for Python |
| **OtodomSpider** | Scrapy spider for otodom.pl |
| **OtodomItem** | Scrapy Item with 30+ fields matching the Property schema |
| **Stealth mode** | Playwright anti-detection measures for web scraping |
| **Agent (AI)** | Automated development agent (PM, Coder, Spec Writer, etc.) |

---

## Additional Documentation

| Document | Path | Purpose |
|----------|------|---------|
| AGENTS.md | `AGENTS.md` | AI agent constitution and development rules |
| Architecture | `doc/overview/02-architecture.md` | System architecture deep-dive |
| North Star | `doc/overview/01-north-star.md` | Product vision and strategy |
| Spec Index | `specs/000-INDEX.md` | 18 specification modules |
| Caching | `doc/overview/08-caching-storage.md` | Redis + MinIO details |
| Backlog | `doc/planning/backlog.md` | Priority-ordered work items |
| ADRs | `doc/decisions/` | Architecture Decision Records |
| ADOS Guide | `doc/guides/change-lifecycle.md` | Change lifecycle process |
