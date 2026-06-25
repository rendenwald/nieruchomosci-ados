# 020 — ARCHITECTURE / System Architecture

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 010-VISION.md
- **AI Context:** Full system map, tech stack, hardware requirements, and all infrastructure diagrams.

---

## Full System Map

```mermaid
graph TB
    subgraph INGRESS["Ingress Layer"]
        CF[Cloudflare Free Tier DDoS + CDN]
        CADDY[Caddy Server Reverse Proxy Auto HTTPS]
    end

    subgraph SCRAPERS["Scraper Layer"]
        OS[otodom-scrapper]
        NS[nieruchomosci-online-scrapper]
        GS[gratka-scrapper]
        SB[scrapper-base]
    end

    subgraph APP["Application Layer"]
        API[FastAPI REST API v1]
        DD[Deduplication Worker]
        ALERT[Alert Worker]
    end

    subgraph STORAGE["Storage Layer"]
        PG[(PostgreSQL 16 + PostGIS)]
        REDIS[(Redis 7 maxmemory 1GB no persist)]
        MINIO[(MinIO standalone mode)]
    end

    subgraph FRONTEND["Frontend Layer"]
        SK[SvelteKit i18n + multi-currency]
        MAP[MapLibre GL Interactive Map]
    end

    subgraph MONITORING["Monitoring Layer"]
        PROM[Prometheus Metrics]
        GRAF[Grafana Dashboards]
        LOKI[Loki Log aggregation retention 7d]
        ALERT_MGR[Alertmanager Notifications]
    end

    subgraph CICD["GitOps / CI/CD"]
        GH[GitHub Actions CI Pipeline]
        ARGOCD[ArgoCD GitOps Deploy]
        REG[GHCR — GitHub Container Registry]
    end

    CF --> CADDY
    CADDY --> SK & API
    SK --> API
    API --> PG & REDIS & MINIO
    SB --> PG & PROM
    DD --> PG
    ALERT --> REDIS & PG
    PROM --> GRAF & ALERT_MGR
    LOKI --> GRAF
    GH --> REG
    REG --> ARGOCD
    ARGOCD --> APP & SCRAPERS
```

---

## Tech Stack (100% Open Source, Self-Hosted)

```mermaid
graph LR
    subgraph "Server / VPS (16 GB RAM)"
        subgraph "k3s (light profile)"
            subgraph "scraper-ns"
                C1[CronJob: otodom]
                C2[CronJob: nieruchomosci]
                C3[CronJob: deduplication]
                C4[CronJob: alert-worker]
            end
            subgraph "app-ns"
                A1[FastAPI 1 replica]
                A2[SvelteKit 1 replica]
                A3[Celery Worker async tasks]
            end
            subgraph "storage-ns"
                D1[(PostgreSQL 16 Primary)]
                D2[(Redis 7 maxmemory 1GB)]
                D3[(MinIO standalone)]
            end
            subgraph "monitoring-ns"
                M1[Prometheus]
                M2[Grafana]
                M3[Loki retention 7d]
                M4[Alertmanager]
            end
            subgraph "gitops-ns"
                G1[ArgoCD 1 replica]
                G2[GitHub + GHCR]
            end
        end
        LB[Caddy Load Balancer Auto HTTPS]
    end
    CF[Cloudflare] --> LB
```

---

## k3s Installation

```bash
curl -sfL https://get.k3s.io | sh -s - \
  --disable=traefik \
  --disable=servicelb \
  --disable=local-storage \
  --disable=metrics-server \
  --flannel-backend=none \
  --write-kubeconfig-mode=644
```

---

## Hardware Requirements (Self-Hosted)

| Component | Minimum | Recommended | Rationale |
|-----------|---------|-------------|-----------|
| CPU | 4 cores | 8 cores | Playwright + k8s overhead |
| RAM | 16 GB | 32 GB | PostgreSQL + Redis + monitoring |
| OS Disk | 50 GB SSD | 100 GB NVMe | System + Docker images |
| Data Disk | 200 GB | 1 TB | PostgreSQL + MinIO photos |
| Network | 100 Mbps | 1 Gbps | Scraping + CDN |

---

## AI Implementation Notes

- Use this module for infrastructure-as-code decisions (k3s, Caddy, namespaces).
- Verify with: `kubectl get nodes`, `kubectl get ns`, `caddy version`.
- Related: 140-GITOPS-CICD.md, 070-DATABASE.md, 120-CACHING-STORAGE.md.
