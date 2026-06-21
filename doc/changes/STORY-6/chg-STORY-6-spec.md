---
change:
  ref: STORY-6
  type: feat
  status: Draft
  slug: alertmanager-alerts
  title: "Send alert via Alertmanager on scraper errors"
  owners: ["rendenwald"]
  service: scrapper-base
  labels: ["change"]
  version_impact: minor
  audience: internal
  security_impact: low
  risk_level: low
  dependencies:
    internal:
      - STORY-1
      - STORY-5
      - STORY-7
      - STORY-8
      - STORY-10
    external: ["Prometheus Pushgateway", "Alertmanager"]
links:
  epic: ../../doc/planning/epics/epic-01--scrapper-base-core/epic-01--scrapper-base-core.md
  spec_modules:
    - ../../specs/130-MONITORING-ALERTS.md
    - ../../specs/020-ARCHITECTURE.md
also_delivers:
  - STORY-12  # Trigger Alertmanager when error_rate > 5%
---

# CHANGE SPECIFICATION

> **PURPOSE**: Add Prometheus alerting to notify the solo developer when scrapers fail or produce excessive errors. This is the operational foundation for running scrapers unattended.

---

## Problem

The project emits Prometheus metrics (`scrape_errors_total`, `listings_scraped_total`, etc.) but there is:

1. **No metrics endpoint** — Prometheus has nothing to scrape. The metrics are defined in code but never exposed.
2. **No alerting** — If a scraper fails (e.g., Otodom changes its HTML structure, network timeout, CAPTCHA block), the developer is not notified. Waking up to a week of missing data is the current failure mode.
3. **No monitoring stack** — The `docker-compose.yml` comment says "Later additions: prometheus, grafana, loki, alertmanager" but only postgres, redis, and minio are configured.

---

## Proposed Solution

Add a lightweight monitoring stack to the MVP docker-compose using the standard Prometheus + Alertmanager + Pushgateway pattern for batch workloads.

### Architecture

```
scraper (batch job)
  │
  │ push_to_gateway() on close_spider()
  ▼
Pushgateway (:9091) ←──── Prometheus (:9090) ←─── Alertmanager (:9093)
                                                                │
                                                                ▼
                                                          Console/log
                                                          (email ready)
```

**Why Pushgateway?** Scrapy spiders are batch processes — they start, scrape, and exit. Prometheus needs a persistent target to scrape. Pushgateway bridges this: the scraper pushes its final metrics on close, and Prometheus scrapes Pushgateway continuously.

### What Changes

**1. `scraper_base/metrics.py`** — Add:
   - `push_metrics()` function that calls `prometheus_client.push_to_gateway()`
   - `scraper_last_run_timestamp` Gauge (epoch seconds, per portal) for the `ScraperNotRunning` alert

**2. `scraper_base/pipeline.py`** — In `close_spider()`:
   - Set `scraper_last_run_timestamp` Gauge to current time
   - Call `push_metrics(PUSHGATEWAY_URL, job_name=PORTAL_SOURCE)` to push all metrics

**3. New config files:**
   - `docker/prometheus/prometheus.yml` — global + scrape configs (Pushgateway, future targets)
   - `docker/prometheus/alert-rules.yml` — alert rules from `130-MONITORING-ALERTS.md`
   - `docker/alertmanager/alertmanager.yml` — receiver config (console/log default, email config template)

**4. `docker-compose.yml`** — Add:
   - `pushgateway` service (prom/pushgateway)
   - `prometheus` service (prom/prometheus) with volume mounts for config
   - `alertmanager` service (prom/alertmanager) with volume mount for config

**5. `scrapper-base/.env.example`** — Add `PUSHGATEWAY_URL` variable

### Alert Rules (from `130-MONITORING-ALERTS.md`)

| Alert | Condition | Severity | Description |
|-------|-----------|----------|-------------|
| `ScraperHighErrorRate` | `rate(scrape_errors_total[15m]) / rate(listings_scraped_total[15m]) > 0.05` for 15m | warning | Error rate exceeds 5% |
| `ScraperNotRunning` | `time() - scraper_last_run_timestamp > 86400` | critical | No scraper run in 24h |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PUSHGATEWAY_URL` | `http://pushgateway:9091` | Pushgateway endpoint for scraper metrics |
| `PROMETHEUS_PORT` | `9090` | Prometheus web interface |
| `ALERTMANAGER_PORT` | `9093` | Alertmanager web interface |

---

## Acceptance Criteria

| ID | Criterion | Verifiable By |
|----|-----------|---------------|
| AC-1 | `close_spider()` pushes metrics to Pushgateway | Unit test with mock `push_to_gateway` |
| AC-2 | `scraper_last_run_timestamp` is set on each run | Unit test inspects Gauge value |
| AC-3 | Prometheus config is valid YAML | `promtool check config` or manual parse |
| AC-4 | Alert rules are valid Prometheus rules | `promtool check rules` or manual parse |
| AC-5 | `docker compose config` parses successfully | `docker compose config --quiet` |
| AC-6 | All existing 51 tests still pass | `pytest` |
| AC-7 | Ruff and mypy --strict pass | Static analysis gates |
| AC-8 | Alertmanager fires `ScraperHighErrorRate` when error rate exceeds 5% | Integration test with test metrics pushed |

---

## Out of Scope

- Grafana dashboards (STORY-11)
- Loki log aggregation (separate story)
- Email/Slack notification delivery beyond console/log receiver
- k8s manifests for monitoring stack (future, when moving from docker-compose to k3s)
- User-facing alerts (STORY-42 through STORY-46)
- SLO recording rules and error budget tracking

## Open Questions

1. **Push frequency**: Should we push on every `close_spider()`, or periodically during the run? Decision: push once on close. Batch metrics are final at that point.

2. **Alertmanager receiver**: Console/log output is the MVP. Should we template an email receiver? Decision: include email config as commented-out template for easy activation.

3. **Metric staleness**: Prometheus will see Pushgateway metrics until they expire (`push_time_seconds` helps). Default Pushgateway doesn't expire metrics automatically — should we add a `--persistence.file` or accept that stale metrics = last known state? Decision: accept last-known-state; the `time() - scraper_last_run_timestamp` check handles staleness.
