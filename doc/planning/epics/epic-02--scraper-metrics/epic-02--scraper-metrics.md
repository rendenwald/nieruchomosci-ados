# Epic 02: Scraper Metrics

> **Goal:** Instrument all scrapers with Prometheus metrics for visibility into scraping operations, performance, and error rates.

## Scope

- Counter metrics for listings scraped
- Error counters with error type labels
- Duration histograms
- DB write performance tracking
- Grafana dashboard for per-portal visibility
- Alertmanager integration for error rate thresholds

## Success Criteria

- Each scraper expose `/metrics` endpoint with Prometheus-format metrics
- Grafana dashboard shows per-portal metrics
- Alert fires when error_rate > 5% over 15 minutes

## Related Spec Modules

- `specs/130-MONITORING-ALERTS.md`
- `specs/060-SCRAPER-BASE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-7 | Track `listings_scraped_total` counter per portal |
| STORY-8 | Increment `scrape_errors_total` with error_type label |
| STORY-9 | Record `scrape_duration_seconds` histogram |
| STORY-10 | Track `db_write_duration_seconds` |
| STORY-11 | Show per-portal dashboard with all metrics in Grafana |
| STORY-12 | Trigger Alertmanager notification when error_rate > 5% |
