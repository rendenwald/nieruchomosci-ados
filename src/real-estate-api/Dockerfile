# =============================================================================
# real-estate-api — Dockerfile
# Multi-stage build with uv
#
# Build context: project root (parent of src/real-estate-api and src/scrapper-base)
# =============================================================================

# ── Stage 1: Install uv and build dependencies ───────────────────────────
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency specifications
COPY src/real-estate-api/pyproject.toml src/real-estate-api/uv.lock ./real-estate-api/
COPY src/scrapper-base/pyproject.toml ./scrapper-base/
COPY src/scrapper-base/src/ ./scrapper-base/src/

# Sync dependencies (frozen = use lock file as-is)
# scrapper-base is installed as editable (path dependency from lock file)
RUN cd real-estate-api && uv sync --no-dev --frozen

# ── Stage 2: Runtime image ───────────────────────────────────────────────
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /app/real-estate-api/.venv /app/.venv

# Copy application source code
COPY src/real-estate-api/app/ ./app/

# Ensure the virtualenv's python is used
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

USER appuser

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
