# 050 — USER-JOURNEYS / Journey Maps

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 010-VISION.md, 020-ARCHITECTURE.md
- **AI Context:** End-to-end user flow maps for three personas: Developer, End User, Admin. Provides UX context for implementation decisions.

---

### Journey 1: Developer — Adding a New Scraper (GitOps Flow)

```
START: Developer wants to add a Gratka scraper
  │
  ▼
[1. Local Setup]
git clone gratka-scrapper
pip install scrapper-base==1.x.x
  │ ✅ 5 minutes
  ▼
[2. Implementation]
class GratkaPipeline(BasePipeline):
    PORTAL_SOURCE = "gratka"
    def item_to_data(self, item): ...
  │ ✅ 2-4 hours (portal logic only)
  ▼
[3. Local Tests]
pytest tests/ -v
scrapy crawl search --dry-run
  │ ✅ Metrics visible at localhost:9090
  ▼
[4. Pull Request]
git push origin feature/gratka-spider
  │ ✅ GitHub Actions: lint → test → build image
  ▼
[5. Merge to main]
CI builds Docker image → pushes to GHCR
  │ ✅ Image: ghcr.io/rendenwald/gratka:v1.0.0
  ▼
[6. ArgoCD auto-deploy]
ArgoCD detects new image → deploy CronJob to k8s
  │ ✅ Scraper runs at 02:00 every night
  ▼
[7. Monitoring]
Grafana shows new "gratka" panel automatically
  │ ✅ Alert if error_rate > 5%
  ▼
END: New portal live in production
⏱️ Time: 1 business day
```

### Journey 2: End User — Searching with Alert

```
START: Anna searches for an apartment in Wrocław
  │
  ▼
[1. Landing Page - PL]
Sees hero: "Find your dream apartment"
Search: Wrocław | Flat | 400k-600k | 50m²+
  │ 💭 "Nice page, professional"
  ▼
[2. Results with Map]
234 offers in list + map with clusters
No duplicates — each property once
  │ 💭 "Great, no repetitions!"
  ▼
[3. Filter on Map]
Draws area: Krzyki and Południe only
Results: 47 offers
  │ 💭 "Exactly these districts I want"
  ▼
[4. Offer Card]
Sees: photo, 520 000 PLN, 62m², 3 rooms
Icons: [Otodom] [Gratka] — same offer on 2 portals
  │ 💭 "I know it's one listing, not a duplicate"
  ▼
[5. Offer Details]
Gallery 12 photos, full description, map location
Section: "Available on portals:" [Otodom↗] [Gratka↗]
  │ 💭 "I can compare comments on both"
  ▼
[6. Create Alert]
Clicks "Set alert" → email when cheaper appears
Configures: max 500k, min 55m², Krzyki
  │ ✅ "Alert set — you'll get an email"
  ▼
[7. Email after 3 days]
"Anna, new offer matches your criteria:
 Flat 58m², 485 000 PLN, Grunwaldzka St. [CHECK]"
  │ 💭 "Perfect! Exactly what I was looking for"
  ▼
END: Anna schedules property viewing
```

### Journey 3: Admin — Monitoring and Alerts

```
START: Monday 08:00, admin checks the platform
  │
  ▼
[1. Grafana Dashboard]
Opens "Platform Overview":
✅ Scrapers: 3/3 operational
✅ API: p95 = 180ms
✅ DB: 23% capacity
✅ Redis: 45% memory
  │ 💭 "All green"
  ▼
[2. Alert at 14:00]
Email: "⚠️ Otodom scraper error_rate = 8% (threshold: 5%)"
Slack: "#alerts: otodom-scrapper failing"
  │ 😟 "Something broke"
  ▼
[3. Diagnosis]
Grafana Loki: logs from last hour
Error: "CSS selector .listing-item not found"
  │ 💭 "Otodom changed HTML"
  ▼
[4. Fix]
git commit -m "fix: update listing selector"
Push → CI → ArgoCD deploy in 3 minutes
  │ ✅ Automatic rollout without downtime
  ▼
[5. Verification]
Grafana: error_rate drops to 0%
Alertmanager: "✅ RESOLVED: otodom error_rate"
  │ ✅ Problem solved in 15 minutes
  ▼
END: Platform healthy
```

---

## AI Implementation Notes

- Use journey flows to validate UI/UX decisions in SvelteKit components.
- Journey 1 maps to: 060-SCRAPER-BASE.md, 140-GITOPS-CICD.md, 130-MONITORING-ALERTS.md.
- Journey 2 maps to: 090-FRONTEND.md, 100-MAP.md, 110-I18N-CURRENCY.md, 120-CACHING-STORAGE.md.
- Journey 3 maps to: 130-MONITORING-ALERTS.md, 140-GITOPS-CICD.md.
- No code generation from this module — purely contextual.
