"""
Prometheus metric definitions for API cache monitoring.

All metrics use the global ``prometheus_client`` registry and are exposed
via the ``/metrics`` endpoint provided by the FastAPI app.

Metrics defined:
- ``cache_hits_total`` — Counter per (endpoint, cache_key_prefix)
- ``cache_misses_total`` — Counter per (endpoint, cache_key_prefix)
- ``cache_errors_total`` — Counter per (endpoint, operation, error_type)
- ``cache_operation_duration_seconds`` — Histogram per (endpoint, operation)
- ``cache_entry_size_bytes`` — Gauge per endpoint
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

cache_hits_total: Counter = Counter(
    "cache_hits_total",
    "Total number of successful cache hits",
    ["endpoint", "cache_key_prefix"],
)

cache_misses_total: Counter = Counter(
    "cache_misses_total",
    "Total number of cache misses (key not found)",
    ["endpoint", "cache_key_prefix"],
)

cache_errors_total: Counter = Counter(
    "cache_errors_total",
    "Total number of Redis errors triggering fallback",
    ["endpoint", "operation", "error_type"],
)

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

CACHE_OPERATION_BUCKETS = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0]

cache_operation_duration_seconds: Histogram = Histogram(
    "cache_operation_duration_seconds",
    "Latency of Redis GET/SET operations in seconds",
    ["endpoint", "operation"],
    buckets=CACHE_OPERATION_BUCKETS,
)

# ---------------------------------------------------------------------------
# Gauges
# ---------------------------------------------------------------------------

cache_entry_size_bytes: Gauge = Gauge(
    "cache_entry_size_bytes",
    "Size of cached response payload in bytes (sampled)",
    ["endpoint"],
)
