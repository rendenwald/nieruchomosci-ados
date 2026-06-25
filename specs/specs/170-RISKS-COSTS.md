# 170 — RISKS-COSTS / Risk Register & Operational Costs

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** all modules
- **AI Context:** Risk assessment and cost breakdown for operations planning.

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Portal changes HTML | High | High | Selector health-check in CI, snapshot tests |
| IP ban by portal | High | Medium | Stealth mode, random delays, rotating UA |
| False duplicates | Medium | Medium | Score >= 0.85 + imageHash verification |
| PostgreSQL disk full | Low | Critical | Alert @ 80%, auto-partitioning |
| scrapper-base breaking change | Low | High | Semver + version pinning in requirements |
| Redis OOM | Low | Medium | maxmemory-policy allkeys-lru, alert @ 90% |
| Exceeding 16 GB RAM | Low | High | RAM monitoring, alert @ 80%, swap |
| MinIO corruption | Low | Critical | Erasure coding + daily external backup |
| GDPR — user data | Medium | High | PII encryption, right to deletion, audit log |
| Competition copying data | Medium | Medium | Rate limiting API, Cloudflare bot protection |

---

## Operational Costs (Self-Hosted)

| Component | Monthly Cost |
|-----------|-------------|
| VPS (Hetzner AX41, 32GB) | ~60 EUR |
| Cloudflare Free | 0 EUR |
| GHCR | 0 EUR |
| PostgreSQL OSS | 0 EUR |
| Redis OSS | 0 EUR |
| MinIO OSS | 0 EUR |
| Grafana OSS | 0 EUR |
| **TOTAL** | **~60 EUR/month** |

---

## AI Implementation Notes

- Incorporate risk mitigations into each module's implementation where relevant:
  - Scraper health checks → 060-SCRAPER-BASE.md
  - Semver → 060-SCRAPER-BASE.md pyproject.toml
  - Disk alerts → 130-MONITORING-ALERTS.md
  - PII encryption → 080-API.md (user model)
  - Rate limiting → 080-API.md middleware
- No code generation from this module — reference only.
