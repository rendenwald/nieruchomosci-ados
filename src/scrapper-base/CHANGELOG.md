# Changelog — scrapper-base

## 0.1.0 (2026-06-20)

- Initial scaffold with package structure and pyproject.toml
- Database: async PostgreSQL engine, SQLAlchemy models, Alembic migration setup
- Services: PropertyService with upsert and Pydantic validation
- Pipeline: BasePipeline ABC with lifecycle hooks
- Metrics: Prometheus counters, histograms, gauges
- Logging: Structured JSON logging via structlog
- Storage: MinIO client with graceful degradation
