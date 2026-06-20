# Epic 10: Monitoring

> **Goal:** Provide comprehensive observability with Prometheus metrics, Grafana dashboards, Loki log aggregation, and Alertmanager notifications.

## Scope

- Prometheus metrics collection (60s scrape interval)
- Grafana dashboards (Platform Overview, Scraper Details, Infrastructure, Business Metrics)
- Loki log aggregation (7-day retention)
- Alertmanager rules for all critical conditions
- SLO definitions and error budget tracking

## Success Criteria

- All dashboards display real-time metrics
- Alerts fire for all defined conditions
- Logs available for last 7 days in Loki

## Related Spec Modules

- `specs/130-MONITORING-ALERTS.md`
- `specs/020-ARCHITECTURE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-47 | Show unified dashboard (scrapers + DB + API + frontend) in Grafana |
| STORY-48 | Alert admin when API p95 latency > 500ms |
| STORY-49 | Alert admin when PostgreSQL connections > 80% |
| STORY-50 | Alert admin when Redis memory > 90% |
| STORY-51 | Alert within 1 minute when container crashes |
| STORY-52 | Alert admin when SvelteKit Core Web Vitals degrade |
