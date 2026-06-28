# Specification: STORY-11 — Grafana Scraper Dashboard (MT-5)

**ref:** STORY-11
**epic:** Epic 2 — Scraper Metrics (MT-5)
**spec modules:** `130-MONITORING-ALERTS.md`, `060-SCRAPER-BASE.md`
**status:** draft

---

## 1. Problem

Scrapers emit Prometheus metrics (`listings_scraped_total`, `scrape_errors_total`,
`scrape_duration_seconds`, etc.) but there is no visual dashboard to monitor them.
Operations staff must query Prometheus directly or check individual endpoint metrics.
A dedicated Grafana dashboard is needed for at-a-glance visibility into scraper health
and performance.

---

## 2. Goals

1. Add Grafana to the local docker-compose development stack
2. Provision Grafana with a Prometheus datasource and a "Scrapers Overview" dashboard
3. Dashboard shows per-portal scraped listing counts, error rates, duration histograms,
   and alert status — refreshed every 30 seconds

---

## 3. Acceptance Criteria

| ID | Criteria |
|----|----------|
| AC-1 | Grafana runs as a Docker container accessible at `http://localhost:3000` |
| AC-2 | Grafana is pre-configured with a Prometheus datasource pointing to `http://prometheus:9090` |
| AC-3 | Dashboard "Scrapers Overview" is pre-provisioned and visible on first login |
| AC-4 | Dashboard includes a **listings chart** showing `rate(listings_scraped_total[5m])` per portal |
| AC-5 | Dashboard includes a **duration histogram** showing p50/p95/p99 of `scrape_duration_seconds` |
| AC-6 | Dashboard includes an **error rate panel** showing `rate(scrape_errors_total[15m]) / rate(listings_scraped_total[15m]) > 0` per portal |
| AC-7 | Dashboard auto-refreshes every 30 seconds |
| AC-8 | Grafana is configured with anonymous access enabled (no login required for local dev) |
| AC-9 | All dashboard panels use the Prometheus datasource defined in AC-2 |

---

## 4. Non-Goals

- No user authentication/authorization (anonymous access for local dev)
- No Loki log integration (separate story: STORY-47/STORY-14)
- No Alertmanager integration in Grafana (alert status shown via Prometheus queries)
- No production-ready Grafana security hardening

---

## 5. Scope

### 5.1 Files to Create

| File | Purpose |
|------|---------|
| `docker/grafana/datasources/prometheus.yml` | Prometheus datasource provisioning YAML |
| `docker/grafana/dashboards/dashboards.yml` | Dashboard provider provisioning YAML |
| `docker/grafana/dashboards/scrapers-overview.json` | Grafana dashboard JSON model |

### 5.2 Files to Modify

| File | Change |
|------|--------|
| `docker-compose.yml` | Add `grafana` service with provisioning volumes |

---

## 6. Dashboard Panels

### Panel 1: Listings Scraped (per portal)
- **Type:** Time series / bar gauge
- **Query:** `rate(listings_scraped_total[5m])`
- **Legend:** `{{portal}}`
- **Unit:** ops/sec

### Panel 2: Scrape Duration (p50, p95, p99)
- **Type:** Time series
- **Query:**
  - p50: `histogram_quantile(0.50, rate(scrape_duration_seconds_bucket[5m]))`
  - p95: `histogram_quantile(0.95, rate(scrape_duration_seconds_bucket[5m]))`
  - p99: `histogram_quantile(0.99, rate(scrape_duration_seconds_bucket[5m]))`
- **Unit:** seconds

### Panel 3: Error Rate (per portal)
- **Type:** Time series
- **Query:** `rate(scrape_errors_total[15m]) / (rate(listings_scraped_total[15m]) > 0 or 1) * 100`
- **Legend:** `{{portal}}`
- **Threshold:** > 5% → red
- **Unit:** percent

### Panel 4: Last Run Timestamp
- **Type:** Stat / Gauge
- **Query:** `time() - scraper_last_run_timestamp{portal="otodom"}`
- **Unit:** seconds (display as "X ago")
- **Threshold:** > 86400 (24h) → red

---

## 7. Dependencies

- Prometheus dashboard must be running and scraping Pushgateway
- Scrapers must push metrics to Pushgateway with `portal` label
- Grafana Docker image `grafana/grafana:latest` (pinned to `11.0.0`)

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Grafana provisioning fails silently | Add healthcheck; verify dashboard loads on first start |
| Dashboard panels return no data | Use "No data" handling in panel options; visible even without data |
