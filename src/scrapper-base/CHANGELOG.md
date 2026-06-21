# Changelog — scrapper-base

## 0.2.0 (2026-06-21)

- **Code review remediation**: TOCTOU race documented, MinIO async wrappers, credential hardening
- **Deep review fixes**: pipeline `wait_for_db()`, logging test validation, mypy strict fixes (dict type args, cast(), unused ignores)
- **Type safety**: All source modules pass `mypy --strict` with zero errors
- **Docker Compose**: Externalized credentials to `.env`, no hardcoded passwords
- **CI**: `uv.lock` committed for reproducible builds

## 0.1.0 (2026-06-20)

- Initial scaffold with package structure and pyproject.toml
- Database: async PostgreSQL engine, SQLAlchemy models, Alembic migration setup
- Services: PropertyService with upsert and Pydantic validation
- Pipeline: BasePipeline ABC with lifecycle hooks
- Metrics: Prometheus counters, histograms, gauges
- Logging: Structured JSON logging via structlog
- Storage: MinIO client with graceful degradation
