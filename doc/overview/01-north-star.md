---
id: NORTH-STAR
status: Draft
created: 2026-06-20
last_updated: 2026-06-20
owners: ["rendenwald"]
summary: "North Star for Real Estate Aggregation Platform — a self-hosted, open-source platform that aggregates Polish real estate listings in one unified, deduplicated, searchable interface."
---

# Real Estate Aggregation Platform: North Star

## Vision

A world where anyone searching for a home in Poland can see **every listing from every portal** in one place — no duplicates, no missed opportunities, fully searchable on an interactive map — powered by a 100% open-source, self-hosted platform that respects user privacy and data sovereignty.

## Mission

We aggregate real estate listings from all major Polish portals (Otodom, Gratka, Nieruchomości Online) by scraping, deduplicating, and presenting them through a unified search interface with interactive map, multi-language support, and smart alerts — so that home seekers never miss a listing and always see the complete picture.

## Target Users

- **Primary:** Polish home seekers looking for apartments, houses, or plots across multiple portals who are tired of checking each portal separately and seeing duplicate listings.
- **Secondary:** Real estate professionals (agents, investors) who need a consolidated view of the market with monitoring and alerting.

## Problem We Solve

- **Portal fragmentation** — Listings are scattered across Otodom, Gratka, Nieruchomości Online, OLX, and more. Checking all of them is tedious and time-consuming.
- **Duplicate listings** — The same property appears on multiple portals with different prices, descriptions, or photos. Users waste time comparing.
- **Missing alerts** — There's no unified alert system across portals. Users miss new listings that match their criteria.
- **Language barriers** — Polish portals are Polish-only. International buyers and renters struggle to search effectively.

## North Star Metric

**Listings viewed per user per week** — the number of unique property listings a user views in a given week. This captures both discovery (searching) and engagement (clicking on listings).

Guardrails: Listing quality score (duplicate rate < 1%), search response time (p95 < 500ms).

## Guiding Principles

- **Open source first** — Every component is open source and self-hosted. No vendor lock-in, no subscription fees.
- **Data quality over quantity** — Better to have 100 clean, deduplicated listings than 500 with duplicates and errors.
- **Privacy by design** — User data stays under the user's control. Self-hosted means zero reliance on third-party data processors.
- **Polish market first** — The platform is built for Poland, with Polish real estate portals, currencies, language, and geographic data as the primary concern. Internationalization is layered on top.

## Decision Filter

When choosing between options, prefer the one that:

1. **Preserves user control** over "makes things easier for the developer"
2. **Improves listing quality** (dedup accuracy, data freshness) over "adds more features"
3. **Reduces operational complexity** over "uses the latest technology"
4. **Serves the MVP scope** (core search + map) over "builds for future scale"

## Scope

**In scope:**

- Scraping from Otodom, Gratka, and Nieruchomości Online portals
- Database-backed property storage with PostGIS spatial indexing
- REST API for property search and filtering
- Interactive map with clusters, markers, and polygon filtering
- Multi-language support (PL/EN/DE/UA)
- Multi-currency support (PLN/EUR/USD/GBP/UAH)
- User accounts with email-based alerts
- Full monitoring stack (Prometheus, Grafana, Loki)

**Out of scope (for now):**

- Mobile native apps (web-first with responsive design)
- Paid listing promotions or featured ads
- Property comparison engine (side-by-side comparison)
- Rental management or tenant tools
- AI-powered price predictions or market analysis

## Current Focus

Building the **scrapper-base core** — the foundational Python package that all scrapers depend on. This is the first dependency for all subsequent work.

Key deliverables:

- Database models and schema (PostgreSQL + PostGIS)
- BasePipeline abstract class for Scrapy scrapers
- Structured logging and Prometheus metrics
- MinIO storage client for photos

Success criteria for this phase:

- A new scraper can be created in < 2 hours by subclassing `BasePipeline`
- Concurrent scrapers can write to the database safely
- Metrics are auto-emitted without manual instrumentation

See [02-architecture.md](./02-architecture.md) for the system architecture overview.

## Stakeholders

- **rendenwald** — Solo developer, architect, operator

---

## Document History

| Date | Author | Change |
|------|--------|--------|
| 2026-06-20 | rendenwald | Initial draft |
