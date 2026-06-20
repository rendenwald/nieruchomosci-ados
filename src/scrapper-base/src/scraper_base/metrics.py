"""
Prometheus metric definitions for scraper monitoring.

All metrics use the global ``prometheus_client`` registry and can be exposed
via any standard ``/metrics`` endpoint.

Metrics defined:
- ``listings_scraped_total`` — Counter per (portal, city, type)
- ``scrape_errors_total`` — Counter per (portal, error_type)
- ``scrape_duration_seconds`` — Histogram per portal
- ``db_write_duration_seconds`` — Histogram per operation (insert/update)
- ``active_listings_gauge`` — Gauge per portal
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

listings_scraped_total: Counter = Counter(
    "listings_scraped_total",
    "Total number of listings scraped",
    ["portal", "city", "type"],
)

scrape_errors_total: Counter = Counter(
    "scrape_errors_total",
    "Total number of scrape errors",
    ["portal", "error_type"],
)

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

SCRAPE_DURATION_BUCKETS = [1, 5, 10, 30, 60, 120, 300, 600]

scrape_duration_seconds: Histogram = Histogram(
    "scrape_duration_seconds",
    "Duration of scraper runs in seconds",
    ["portal"],
    buckets=SCRAPE_DURATION_BUCKETS,
)

DB_WRITE_BUCKETS = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]

db_write_duration_seconds: Histogram = Histogram(
    "db_write_duration_seconds",
    "Duration of database write operations in seconds",
    ["operation"],
    buckets=DB_WRITE_BUCKETS,
)

# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

active_listings_gauge: Gauge = Gauge(
    "active_listings_gauge",
    "Current number of active listings",
    ["portal"],
)

# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def increment_listings_scraped(
    portal: str,
    city: str = "unknown",
    property_type: str = "unknown",
) -> None:
    """Increment the ``listings_scraped_total`` counter."""
    listings_scraped_total.labels(portal=portal, city=city, type=property_type).inc()


def increment_errors(portal: str, error_type: str = "unknown") -> None:
    """Increment the ``scrape_errors_total`` counter."""
    scrape_errors_total.labels(portal=portal, error_type=error_type).inc()


def observe_scrape_duration(portal: str, duration_seconds: float) -> None:
    """Record a scrape duration observation."""
    scrape_duration_seconds.labels(portal=portal).observe(duration_seconds)


def observe_db_write(operation: str, duration_seconds: float) -> None:
    """Record a database write duration observation."""
    db_write_duration_seconds.labels(operation=operation).observe(duration_seconds)


def set_active_listings(portal: str, count: int) -> None:
    """Set the active listings gauge for a portal."""
    active_listings_gauge.labels(portal=portal).set(count)
