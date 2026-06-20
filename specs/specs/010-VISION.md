# 010 — VISION / Platform Vision

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** none
- **AI Context:** High-level vision and fundamental principles. Read first to understand the "why".

---

## Platform Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                    PLATFORMA NIERUCHOMOŚCI                      │
│                                                                 │
│  Scrapery → scrapper-base → PostgreSQL/PostGIS → FastAPI         │
│       ↓                                                         │
│  Deduplikacja → Redis Cache → SvelteKit Portal                  │
│       ↓                                                         │
│  Monitoring → Alerty → GitOps CI/CD → Self-hosted               │
└─────────────────────────────────────────────────────────────────┘
```

### Fundamental Principles

- **100% Open Source** — zero kosztów licencji
- **Self-hosted** — własny serwer, pełna kontrola danych
- **GitOps** — infrastruktura jako kod, pełna historia zmian
- **Skalowalne** — od 1 serwera do klastra Kubernetes
- **Multi-język / Multi-waluta** — PL/EN/DE/UA + PLN/EUR/USD

---

## AI Implementation Notes

This module is informational only — it sets context. No code generation required.
