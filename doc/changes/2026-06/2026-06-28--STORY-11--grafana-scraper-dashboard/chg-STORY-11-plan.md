# Implementation Plan: STORY-11 — Grafana Scraper Dashboard (MT-5)

**ref:** STORY-11
**status:** draft

---

## Phase 1: Create Grafana provisioning files

### Task 1.1: Create `docker/grafana/datasources/prometheus.yml`

Grafana datasource provisioning YAML that configures a Prometheus datasource
pointing to the `prometheus` service in the Docker network.

**Key details:**
- Name: `Prometheus`
- Type: `prometheus`
- URL: `http://prometheus:9090`
- Access: `proxy`
- `isDefault: true`

### Task 1.2: Create `docker/grafana/dashboards/dashboards.yml`

Dashboard provider YAML that tells Grafana to load dashboard JSON files from
the provisioning directory.

**Key details:**
- Provider name: `Scrapers`
- Folder: `Scrapers`
- Type: `file`
- Path: `/etc/grafana/provisioning/dashboards`

### Task 1.3: Create `docker/grafana/dashboards/scrapers-overview.json`

Grafana dashboard JSON model with 4 panels:

1. **Listings Scraped** — Time series, `rate(listings_scraped_total[5m])` by `portal`
2. **Scrape Duration** — Time series, histogram_quantile p50/p95/p99
3. **Error Rate** — Time series, error rate % by portal, threshold at 5%
4. **Last Run** — Stat panel showing time since last run

**Key settings:**
- `refresh: 30s`
- `time.from: now-1h`
- Datasource: `Prometheus` (via `$datasource` template variable)

---

## Phase 2: Update docker-compose.yml

### Task 2.1: Add Grafana service

Add a `grafana` service to `docker-compose.yml`:

```yaml
grafana:
  image: grafana/grafana:11.0.0
  container_name: realestate-grafana
  restart: unless-stopped
  ports:
    - "${GRAFANA_PORT:-3000}:3000"
  environment:
    GF_AUTH_ANONYMOUS_ENABLED: "true"
    GF_AUTH_ANONYMOUS_ORG_ROLE: "Admin"
    GF_SECURITY_ADMIN_USER: "${GRAFANA_ADMIN_USER:-admin}"
    GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:-admin}"
  volumes:
    - ./docker/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    - ./docker/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    - grafana_data:/var/lib/grafana
  healthcheck:
    test: ["CMD", "wget", "-q", "--tries=1", "--timeout=3", "http://localhost:3000/api/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
  networks:
    - realestate-net
```

### Task 2.2: Add `grafana_data` volume

Add `grafana_data:` to the `volumes:` section.

### Task 2.3: Comment out the "Future additions" note

Update the Grafana comment in docker-compose.yml from "Future additions" to "Now added".

---

## Phase 3: Add verification script

### Task 3.1: Create `scripts/verify-grafana.sh`

Shell script that:
1. Checks Grafana health API
2. Verifies Prometheus datasource exists
3. Verifies Scrapers Overview dashboard exists

---

## Phase 4: Verify

### Task 4.1: Run verification

```bash
docker compose up -d grafana
docker compose ps  # confirm healthy
./scripts/verify-grafana.sh  # API checks
```

### Task 4.2: Manual inspection

Open http://localhost:3000 → verify dashboard loads without authentication
