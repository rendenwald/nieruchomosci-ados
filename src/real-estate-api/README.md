# real-estate-api

FastAPI REST API for the Real Estate Aggregation Platform.

Provides a Redis-cached `GET /api/v1/properties` endpoint with async PostgreSQL
backed by the `scrapper-base` package.

## Features

- **Cache-aside** with Redis — deterministic SHA-256 cache keys from query params
- **Thundering herd prevention** — `SET NX` lock ensures one DB query per unique filter set
- **Graceful degradation** — transparent DB fallback when Redis is unavailable
- **X-Cache headers** — `hit` / `miss` / `miss (fallback)` on every response
- **Prometheus metrics** — cache hits, misses, errors, operation latency
- **Health check** — `GET /health` with Redis connectivity status

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- PostgreSQL 16+ with async driver (`asyncpg`)
- Redis 7+

### Local Development

```bash
# Create virtualenv and install dependencies
uv sync

# Copy environment configuration
cp .env.example .env

# Start the development server
uv run uvicorn app.main:create_app --factory --reload --port 8000

# Run tests
uv run pytest tests/ -v --cov=app
```

### Docker Compose

```bash
# From the repository root:
docker compose up -d real-estate-api

# The API will be available at http://localhost:8000
# API docs: http://localhost:8000/api/v1/docs
# Health:   http://localhost:8000/health
```

## Environment Variables

See `.env.example` for all configurable variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `REDIS_POOL_SIZE` | `10` | Max connections in Redis pool |
| `REDIS_TIMEOUT_SECONDS` | `2` | Timeout for Redis operations |
| `REDIS_HEALTH_CHECK_INTERVAL` | `30` | Seconds between Redis health checks |
| `REDIS_HEALTH_CHECK_FAILURE_THRESHOLD` | `3` | Consecutive failures before degraded mode |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/realestate` | Async PostgreSQL DSN |
| `CACHE_TTL_SECONDS` | `120` | Default TTL for cached responses |
| `CACHE_KEY_PREFIX` | `properties:list:v1` | Prefix for Redis cache keys |
| `API_PREFIX` | `/api/v1` | Base path for API routes |
| `PROPERTIES_MAX_LIMIT` | `100` | Hard upper bound for pagination limit |
| `PROPERTIES_DEFAULT_LIMIT` | `20` | Default items per page |
| `METRICS_ENABLED` | `true` | Expose Prometheus metrics |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/properties` | Paginated list with filters, sorting, cache-aside |
| `GET` | `/health` | Health status with Redis connectivity |

### Query Parameters (`GET /api/v1/properties`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `city` | `string` | — | City name (partial, case-insensitive) |
| `property_type` | `string` | — | `apartment`, `house`, `plot`, etc. |
| `auction_type` | `string` | — | Auction type filter |
| `market_type` | `string` | — | Primary/secondary market |
| `price_min` | `int` | — | Minimum price (>= 0) |
| `price_max` | `int` | — | Maximum price (>= 0) |
| `area_min` | `float` | — | Minimum area (>= 0) |
| `area_max` | `float` | — | Maximum area (>= 0) |
| `rooms` | `string` | — | Number of rooms (exact match) |
| `sort_by` | `string` | `last_seen_at:desc` | Sort `field:direction` |
| `page` | `int` | `1` | Page number (>= 1) |
| `limit` | `int` | `20` | Items per page (1–100) |

### Response Shape

```json
{
  "items": [
    {
      "id": 12345,
      "title": "Mieszkanie 2 pokoje, Warszawa Mokotów",
      "property_type": "apartment",
      "price": 450000,
      "price_currency": "PLN",
      "price_per_m2": 15000,
      "area": 30.0,
      "rooms": "2",
      "city": "Warszawa",
      "district": "Mokotów",
      "province": "mazowieckie",
      "latitude": 52.1934,
      "longitude": 21.0219,
      "agency_name": "Agencja Nieruchomości XYZ",
      "photos": ["https://..."],
      "source_url": "https://...",
      "portal_source": "otodom",
      "created_at": "2026-06-21T12:00:00"
    }
  ],
  "total": 150,
  "page": 1,
  "limit": 20,
  "total_pages": 8
}
```

## Running Tests

```bash
# Full test suite with coverage
uv run pytest tests/ -v --cov=app --cov-report=term

# Specific test file
uv run pytest tests/test_cache_service.py -v

# Ruff linting
uv run ruff check .

# Type checking
uv run mypy app/
```

## Project Structure

```
src/real-estate-api/
├── app/
│   ├── __init__.py              # Package metadata (version)
│   ├── main.py                  # FastAPI app factory, lifespan, router registration
│   ├── core/
│   │   ├── __init__.py          # Exports Settings and get_settings
│   │   ├── config.py            # pydantic-settings configuration class
│   │   └── metrics.py           # Prometheus metric definitions
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── properties.py        # GET /api/v1/properties with cache-aside
│   │   └── health.py            # GET /health endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py            # PaginatedResponse, ErrorResponse
│   │   └── property.py          # PropertyCard, SearchParams, SearchResponse
│   └── services/
│       ├── __init__.py
│       ├── cache_key.py         # Deterministic SHA-256 cache key generation
│       ├── cache_service.py     # Cache-aside get_or_compute with thundering herd lock
│       ├── property_service.py  # SQLAlchemy query builder, search execution
│       └── redis_client.py      # Async Redis client with connection pool, health tracking
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # fakeredis fixtures, test app, async HTTP client
│   ├── test_cache_key.py        # 11 tests: deterministic keys, normalization, SHA-256
│   ├── test_cache_service.py    # 6 tests: miss/hit, TTL, fallback, degraded, dedup
│   ├── test_health.py           # 4 tests: health endpoint, redis status
│   └── test_properties.py       # 12 tests: endpoint, X-Cache, validation, sort
├── Dockerfile                   # Multi-stage build with uv
├── pyproject.toml               # Project metadata, dependencies, tool config
└── README.md                    # This file
```
