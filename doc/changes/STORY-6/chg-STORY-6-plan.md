---
id: chg-STORY-6-alertmanager-alerts
status: Draft
created: 2026-06-21
last_updated: 2026-06-21
owners: [rendenwald]
service: scrapper-base
labels: [change]
links:
  change_spec: ./chg-STORY-6-spec.md
summary: >
  Add Prometheus-based alerting for scraper failures. Scraper pushes metrics
  to Pushgateway on close; Prometheus scrapes Pushgateway; Alertmanager fires
  rules when error rates exceed 5% or scrapers stop running.
version_impact: minor
also_delivers:
  - STORY-12
---

# IMPLEMENTATION PLAN — STORY-6: Send alert via Alertmanager on scraper errors

## Context

The project emits Prometheus metrics (`scrape_errors_total`, `listings_scraped_total`, etc.) but has no monitoring stack. Scrapers are batch processes — they start, scrape, exit. We need:

1. A way to expose batch metrics persistently → **Pushgateway**
2. A scraper to collect metrics → **Prometheus**
3. A rule evaluator + notifier → **Alertmanager**

This plan adds all three to `docker-compose.yml` and wires `BasePipeline.close_spider()` to push final metrics on each run.

## Scope

### In Scope
- `scraper_base/metrics.py`: Add `push_metrics()` + `scraper_last_run_timestamp`
- `scraper_base/pipeline.py`: Push metrics in `close_spider()`
- `docker/prometheus/prometheus.yml`: Prometheus scrape config
- `docker/prometheus/alert-rules.yml`: ScraperHighErrorRate + ScraperNotRunning rules
- `docker/alertmanager/alertmanager.yml`: Console receiver (email ready)
- `docker-compose.yml`: Add pushgateway, prometheus, alertmanager services
- `scrapper-base/.env.example`: Add `PUSHGATEWAY_URL`

### Out of Scope
- Grafana dashboards (STORY-11)
- Email/Slack receiver wiring (config template only)
- Loki log aggregation
- k8s monitoring manifests

## Phases

### Phase 1: Metrics Push + Last-Run Timestamp

**Goal:** Add `push_metrics()` helper and `scraper_last_run_timestamp` gauge to the Python package.

**Tasks:**
- [x] 1.1 Add `scraper_last_run_timestamp` Gauge to `metrics.py`:
- [x] 1.2 Add `push_metrics()` function to `metrics.py`:
- [x] 1.3 Import `push_to_gateway` and `REGISTRY` from `prometheus_client`:
- [x] 1.4 In `BasePipeline.close_spider()`, add before cleanup:
- [x] 1.5 In `BasePipeline.close_spider()`, set the last-run timestamp:
- [x] 1.6 Add `import os` and `import time` to pipeline.py (time already imported)

**Acceptance criteria:**
- [x] `push_metrics()` pushes all metrics via `push_to_gateway()`
- [x] `scraper_last_run_timestamp` is set on `close_spider()`
- [x] Ruff clean (imports, unused vars)
- [x] Mypy --strict passes

**Files:**
- `src/scrapper-base/src/scraper_base/metrics.py`
- `src/scrapper-base/src/scraper_base/pipeline.py`

### Phase 2: Infrastructure Config Files

**Goal:** Create Prometheus, Alertmanager, and Pushgateway configuration files.

**Tasks:**
- [x] 2.1 Create `docker/prometheus/` directory
- [x] 2.2 Create `docker/prometheus/prometheus.yml`:
      ```yaml
      global:
        scrape_interval: 15s
        evaluation_interval: 15s
      
      rule_files:
        - "alert-rules.yml"
      
      scrape_configs:
        - job_name: "pushgateway"
          honor_labels: true
          static_configs:
            - targets: ["pushgateway:9091"]
      ```
- [x] 2.3 Create `docker/prometheus/alert-rules.yml` with rules from spec:
      ```yaml
      groups:
        - name: scrapers
          rules:
            - alert: ScraperHighErrorRate
              expr: |
                rate(scrape_errors_total[15m]) /
                rate(listings_scraped_total[15m]) > 0.05
              for: 15m
              labels:
                severity: warning
              annotations:
                summary: "Scraper {{ $labels.portal }} error rate > 5%"
                description: "Error rate: {{ $value | humanizePercentage }}"
      
            - alert: ScraperNotRunning
              expr: |
                time() - scraper_last_run_timestamp > 86400
              labels:
                severity: critical
              annotations:
                summary: "Scraper {{ $labels.portal }} not run > 24h"
                description: "Last run: {{ $value | humanizeDuration }} ago"
      ```
- [x] 2.4 Create `docker/alertmanager/` directory
- [x] 2.5 Create `docker/alertmanager/alertmanager.yml`:
      ```yaml
      route:
        receiver: "console"
        group_wait: 30s
        group_interval: 5m
        repeat_interval: 4h
        routes:
          - receiver: "console"
            continue: true
      
      receivers:
        - name: "console"
          webhook_configs:
            - url: "http://localhost:9093/alertmanager/-/reload"
              send_resolved: true
      
      # Uncomment below to enable email alerts:
      # receivers:
      #   - name: "email"
      #     email_configs:
      #       - to: "admin@domain.pl"
      #         from: "alertmanager@domain.pl"
      #         smarthost: "smtp.example.com:587"
      #         auth_username: "alertmanager@domain.pl"
      #         auth_password: "${SMTP_PASSWORD}"   # env var
      #         require_tls: true
      ```

**Acceptance criteria:**
- [x] `prometheus.yml` is valid YAML
- [x] `alert-rules.yml` is valid Prometheus rule syntax
- [x] `alertmanager.yml` is valid YAML

**Files:**
- `docker/prometheus/prometheus.yml`
- `docker/prometheus/alert-rules.yml`
- `docker/alertmanager/alertmanager.yml`

### Phase 3: Docker Compose Expansion

**Goal:** Add Pushgateway, Prometheus, and Alertmanager to the local development stack.

**Tasks:**
- [x] 3.1 Add Pushgateway service:
      ```yaml
      pushgateway:
        image: prom/pushgateway
        container_name: realestate-pushgateway
        restart: unless-stopped
        ports:
          - "${PUSHGATEWAY_PORT:-9091}:9091"
        networks:
          - realestate-net
      ```
- [x] 3.2 Add Prometheus service:
      ```yaml
      prometheus:
        image: prom/prometheus
        container_name: realestate-prometheus
        restart: unless-stopped
        ports:
          - "${PROMETHEUS_PORT:-9090}:9090"
        volumes:
          - ./docker/prometheus:/etc/prometheus:ro
          - prometheus_data:/prometheus
        command:
          - "--config.file=/etc/prometheus/prometheus.yml"
          - "--storage.tsdb.path=/prometheus"
          - "--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-15d}"
        networks:
          - realestate-net
      ```
- [x] 3.3 Add Alertmanager service:
      ```yaml
      alertmanager:
        image: prom/alertmanager
        container_name: realestate-alertmanager
        restart: unless-stopped
        ports:
          - "${ALERTMANAGER_PORT:-9093}:9093"
        volumes:
          - ./docker/alertmanager:/etc/alertmanager:ro
          - alertmanager_data:/alertmanager
        command:
          - "--config.file=/etc/alertmanager/alertmanager.yml"
          - "--storage.path=/alertmanager"
        networks:
          - realestate-net
      ```
- [x] 3.4 Add new volumes:
      ```yaml
      volumes:
        prometheus_data:
        alertmanager_data:
      ```
- [x] 3.5 Add env vars to comment block at top of docker-compose.yml
- [x] 3.6 Update the "Later additions" comment to note which services are now included

**Acceptance criteria:**
- [x] `docker compose config` parses without errors
- [x] New services appear in `docker compose ps`

**Files:**
- `docker-compose.yml`

### Phase 4: Configuration & Environment

**Goal:** Add env var documentation for the new services.

**Tasks:**
- [x] 4.1 Add `PUSHGATEWAY_URL` to `src/scrapper-base/.env.example`
- [x] 4.2 Add `PUSHGATEWAY_PORT`, `PROMETHEUS_PORT`, `ALERTMANAGER_PORT`, `PROMETHEUS_RETENTION` to a root `.env.example` if it exists (check first)
- [x] 4.3 Add `.env.example` entries for SMTP config (commented out, for future email alerts)

**Files:**
- `src/scrapper-base/.env.example`
- `.env.example` (if exists)

### Phase 5: Tests

**Goal:** Verify metrics push, timestamp setting, and config validity.

**Tasks:**
- [x] 5.1 Add test for `push_metrics()`:
      ```python
      async def test_push_metrics(mock_pushgateway):
          """push_metrics calls push_to_gateway with correct args."""
          from scraper_base.metrics import push_metrics
      
          push_metrics("http://localhost:9091", "test-portal")
          # Assert push_to_gateway was called with job="test-portal"
      ```
- [x] 5.2 Add test for `scraper_last_run_timestamp` in `close_spider()`:
      ```python
      async def test_close_spider_sets_timestamp(pipeline_instance):
          """close_spider sets scraper_last_run_timestamp gauge."""
          await pipeline_instance.close_spider()
          # Verify the gauge has a value for PORTAL_SOURCE
      ```
- [x] 5.3 Add test for alert rules YAML validity:
      ```python
      def test_alert_rules_valid_yaml():
          """alert-rules.yml is valid YAML."""
          import yaml
          with open("docker/prometheus/alert-rules.yml") as f:
              data = yaml.safe_load(f)
          assert "groups" in data
      ```
- [x] 5.4 Add test for docker-compose config parsing (optional — if `docker compose` is available)

**Files:**
- `src/scrapper-base/tests/test_metrics.py` (add to existing)
- `src/scrapper-base/tests/test_pipeline.py` (add to existing)
- `src/scrapper-base/tests/test_infrastructure.py` (new — config validation tests)

### Phase 6: Verification

**Goal:** Final quality gates before PR.

**Tasks:**
- [x] 6.1 Run verification checklist:
      ```bash
      uv run ruff check src/scrapper-base/
      uv run mypy src/scrapper-base/src/scraper_base/ --strict
      uv run pytest src/scrapper-base/tests/ -v
      ```
- [x] 6.2 Update backlog: mark STORY-6 in-progress (→ done after merge)

**Acceptance criteria:**
- [x] All lint, type check, and test gates pass

### Phase 7: Pull Request

**Goal:** Merge STORY-6 into main.

**Tasks:**
- [x] 7.1 Create feature branch: `feature/STORY-6-alertmanager-alerts`
- [x] 7.2 Commit all changes with conventional commit message
- [x] 7.3 Create PR with title: `[STORY-6] Alertmanager alerts for scraper errors`
- [x] 7.4 Squash merge into main

## Revision Log

| Date | Author | Change |
|------|--------|--------|
| 2026-06-21 | rendenwald | Initial plan |
| 2026-06-21 | rendenwald | Completed: metric push + timestamp, infra config, docker-compose, tests, verification |
