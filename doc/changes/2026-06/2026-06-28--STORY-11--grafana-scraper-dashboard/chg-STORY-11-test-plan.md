# Test Plan: STORY-11 — Grafana Scraper Dashboard (MT-5)

**ref:** STORY-11
**status:** draft

---

## 1. Verification Strategy

Grafana dashboard provisioning is verified through:
1. **Docker healthcheck** — container starts and responds
2. **Provisioning check** — datasource and dashboard are loaded by Grafana on startup
3. **API smoke tests** — verify Grafana API returns expected state
4. **Manual visual inspection** — dashboard panels render correctly

---

## 2. Automated Tests

### 2.1 Grafana container healthcheck (docker-compose.yml)

```yaml
healthcheck:
  test: ["CMD", "wget", "-q", "--tries=1", "--timeout=3", "http://localhost:3000/api/health"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

### 2.2 Grafana API verification script

Create `scripts/verify-grafana.sh`:

```bash
#!/usr/bin/env bash
# Verify Grafana provisioning
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"

# 1. Health check
curl -sf "$GRAFANA_URL/api/health" | jq -e '.database == "ok"'

# 2. Datasource check — Prometheus datasource exists
curl -sf "$GRAFANA_URL/api/datasources" | jq -e '.[] | select(.name == "Prometheus")'

# 3. Dashboard check — Scrapers Overview exists
curl -sf "$GRAFANA_URL/api/search?query=Scrapers%20Overview" | jq -e 'length > 0'

echo "All checks passed."
```

---

## 3. Manual Verification Steps

### 3.1 Start the stack

```bash
docker compose up -d prometheus grafana
```

### 3.2 Verify Grafana is running

```bash
curl http://localhost:3000/api/health
# Expected: {"database":"ok", ...}
```

### 3.3 Verify Prometheus datasource

1. Open http://localhost:3000
2. Go to **Connections → Data Sources → Prometheus**
3. Verify URL is `http://prometheus:9090` and "Test" passes

### 3.4 Verify dashboard is provisioned

1. Go to **Dashboards → Scrapers Overview**
2. Each panel should display (may show "No data" if no scrapers have run)

### 3.5 Verify AC items

| AC | Verification |
|----|-------------|
| AC-1 | `curl http://localhost:3000` returns Grafana login page |
| AC-2 | Prometheus datasource configured and test passes |
| AC-3 | Dashboard visible in Grafana UI |
| AC-4 | Listings panel exists with query for `listings_scraped_total` |
| AC-5 | Duration panel exists with histogram query |
| AC-6 | Error rate panel exists with error rate query |
| AC-7 | Dashboard auto-refresh set to 30s |
| AC-8 | Anonymous access enabled (no login required) |
| AC-9 | All panels use Prometheus datasource |

---

## 4. Edge Cases

| Edge Case | Expected |
|-----------|----------|
| No metrics emitted yet | Panels show "No data" gracefully |
| Grafana starts before Prometheus | Provisioning succeeds; datasource test may fail until Prometheus is ready |
| Grafana container restarts | Provisioning re-applies on every start; dashboards persist via named volume (or are re-provisioned from files) |
