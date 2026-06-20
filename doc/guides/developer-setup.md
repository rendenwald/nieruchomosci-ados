---
id: DEV-SETUP
status: Draft
created: 2026-06-20
last_updated: 2026-06-20
owners: ["rendenwald"]
summary: "Local development environment setup guide for the Real Estate Aggregation Platform."
---

# Developer Setup Guide

> **Platform:** Ubuntu (WSL 2)
> **Last verified:** 2026-06-20

---

## 1. Overview of Required Tools

| Tool | Version | Purpose | Required? |
|------|---------|---------|-----------|
| Python | 3.12+ | Backend (FastAPI, Scrapy) | Required |
| uv | ≥0.11 | Python package & virtualenv manager | Required |
| Node.js | ≥20 LTS | Frontend (SvelteKit) | Required |
| PostgreSQL | 16 + PostGIS | Primary database | Required |
| Redis | 7 | Caching, streams | Required |
| Playwright | latest | Scraping (browser automation) | Required |
| Docker | latest | Local infra containers | Recommended |
| MinIO | latest | Photo storage | Required (via Docker) |
| gh | ≥2.50 | GitHub CLI for PR operations | Required |

---

## 2. Python Setup

Python 3.12.3 is already installed. All Python dependencies are managed with **uv**.

```bash
# Verify Python
python3 --version

# Verify uv (already installed)
uv --version

# Create virtualenv and install dependencies (when src/ exists)
# uv sync
```

**What is uv?** A fast Python package and project manager (replaces pip + venv + poetry). It creates isolated virtual environments per project.

---

## 3. Node.js Installation

Node.js is **not installed**. Install it via `nvm` (Node Version Manager):

```bash
# Step 1: Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash

# Step 2: Reload shell config
source ~/.bashrc

# Step 3: Install Node.js LTS
nvm install 22
nvm alias default 22

# Step 4: Verify
node --version   # Should be v22.x
npm --version    # Should be 10.x
```

**Alternative — direct install (if nvm doesn't work):**

```bash
# Using NodeSource Ubuntu PPA
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
node --version
```

---

## 4. PostgreSQL + PostGIS

```bash
# Step 1: Install PostgreSQL 16 and PostGIS
sudo apt-get update
sudo apt-get install -y postgresql-16 postgresql-16-postgis-3

# Step 2: Start the service
sudo service postgresql start

# Step 3: Create database user (match your app config)
sudo -u postgres createuser --superuser $USER

# Step 4: Create development database
createdb real_estate_dev

# Step 5: Enable PostGIS extension
psql -d real_estate_dev -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Step 6: Verify
psql --version
psql -d real_estate_dev -c "SELECT PostGIS_Full_Version();"
```

**Connection string:** `postgresql+asyncpg://localhost:5432/real_estate_dev`

---

## 5. Redis

```bash
# Install Redis 7
curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/debian $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
sudo apt-get update
sudo apt-get install -y redis

# Start Redis
sudo service redis-server start

# Verify
redis-cli ping  # Should return PONG
```

---

## 6. Playwright

```bash
# Install Playwright Python package (when src/ exists)
# uv add --dev pytest-playwright

# Install Chromium browser binary
playwright install chromium

# Verify
playwright --version
```

---

## 7. Docker Environment

Docker is **not installed**. Two options below.

### 7.1 Option A: Docker Desktop with WSL 2 (Recommended for beginners)

Docker Desktop provides a GUI, automatic WSL integration, and comes with Docker Compose.

```bash
# Step 1: Download Docker Desktop for Windows
# https://docs.docker.com/desktop/setup/install/windows-install/

# Step 2: Install and enable WSL 2 integration
#   - Open Docker Desktop → Settings → Resources → WSL Integration
#   - Enable integration for your Ubuntu WSL distro

# Step 3: Verify in WSL terminal
docker --version
docker compose version

# Step 4: (Optional) Buildx for multi-platform builds
docker buildx version
```

### 7.2 Option B: Docker Engine native in WSL (Lighter, no GUI)

```bash
# Install Docker Engine directly in WSL
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2

# Add your user to the docker group (avoids sudo)
sudo usermod -aG docker $USER

# Start Docker
sudo service docker start

# Verify
docker --version
docker compose version
```

> **Recommendation:** Option A (Docker Desktop) is simpler for WSL — it handles the Docker daemon lifecycle automatically and provides better integration.

### 7.3 Running services via Docker Compose

Once Docker is set up, you can run all infrastructure services:

```bash
# Start all services (PostgreSQL, Redis, MinIO)
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

Example `docker-compose.yml` (to be created in project root):

```yaml
services:
  postgres:
    image: postgis/postgis:16-3.4
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: ${USER}
      POSTGRES_DB: real_estate_dev
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: ["redis-server", "--maxmemory", "1gb", "--maxmemory-policy", "allkeys-lru", "--save", "", "--appendonly", "no"]

  minio:
    image: minio/minio:latest
    ports: ["9000:9000", "9001:9001"]
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin123
    volumes: [miniodata:/data]

volumes:
  pgdata:
  miniodata:
```

---

## 8. Local Kubernetes Overview

Two approaches for running the application locally:

### 8.1 Option A: Docker Compose (Simpler, Recommended for MVP)

| Aspect | Details |
|--------|---------|
| **Setup time** | 5 minutes |
| **Resource usage** | Low |
| **K8s features** | None (no auto-scaling, no self-healing) |
| **Best for** | Local development, testing, MVP |
| **Services** | PostgreSQL, Redis, MinIO via `docker compose up` |
| **Scrapers** | Run manually via `scrapy crawl` |
| **FastAPI** | Run via `uv run uvicorn` |

**How to run:**
```bash
docker compose up -d          # Start infra services
uv run uvicorn app.main:app   # Start API
npm run dev                   # Start frontend
```

### 8.2 Option B: k3s (Closer to Production, More Complex)

| Aspect | Details |
|--------|---------|
| **Setup time** | 15-20 minutes |
| **Resource usage** | Medium (needs ~2GB RAM for k3s) |
| **K8s features** | Full (CronJobs, auto-healing, namespaces) |
| **Best for** | Production simulation, testing CronJobs |
| **Services** | All defined as k8s manifests in `k8s/` |
| **Scrapers** | Run as CronJobs |
| **FastAPI** | Run as Deployment with Service |

**Installation:**
```bash
# Install k3s (lightweight Kubernetes)
curl -sfL https://get.k3s.io | sh -s - \
  --disable=traefik \
  --disable=servicelb \
  --write-kubeconfig-mode=644

# Verify
kubectl get nodes

# Deploy application
kubectl apply -f k8s/namespaces/
kubectl apply -f k8s/storage/
kubectl apply -f k8s/app/
```

**Port mapping for local access:**
```bash
# Port-forward services for local access
kubectl port-forward -n app-ns svc/fastapi 8000:8000
kubectl port-forward -n app-ns svc/sveltekit 5173:5173
```

### 8.3 Decision: Docker Compose vs k3s

| Consideration | Choose Docker Compose | Choose k3s |
|---------------|----------------------|------------|
| Development speed | ✅ Faster iteration | ❌ Slower (k8s manifests) |
| Learning curve | ✅ Simple | ❌ Steeper |
| Production parity | ❌ Far from prod | ✅ Near-identical |
| CronJobs | ❌ Manual triggers | ✅ Built-in |
| Resource usage | ✅ ~1GB RAM | ⚠️ ~2-3GB RAM |
| **Recommendation** | **MVP / Sprint 1-3** | **Sprint 4+** |

> **Recommended path:** Start with Docker Compose for rapid development. Switch to k3s when you need to test CronJobs (scrapers, dedup) and GitOps deployment.

---

## 9. GitHub CLI

`gh` is already installed (v2.95.0). If authentication is needed:

```bash
# Authenticate with GitHub
gh auth login

# Verify
gh repo view rendenwald/nieruchomosci-ados
```

---

## 10. Quick Verification Script

Run this to verify everything is installed:

```bash
echo "=== Python ===" && python3 --version
echo "=== uv ===" && uv --version
echo "=== Node.js ===" && node --version
echo "=== npm ===" && npm --version
echo "=== PostgreSQL ===" && psql --version
echo "=== Redis ===" && redis-cli --version
echo "=== Docker ===" && docker --version
echo "=== Docker Compose ===" && docker compose version
echo "=== gh ===" && gh --version
echo "=== Playwright ===" && npx playwright --version
```

---

## 11. Environment Variables

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://localhost:5432/real_estate_dev

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=property-photos

# GitHub (for PR operations)
GH_TOKEN=ghp_...
```

> **Never commit `.env` to git.** Add it to `.gitignore` if not already there.

---

## Document History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-20 | rendenwald | Initial draft |
