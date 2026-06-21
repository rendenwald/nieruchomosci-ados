"""Tests for Prometheus metric definitions and helpers."""

from unittest.mock import patch

from prometheus_client import REGISTRY

from scraper_base.metrics import (
    active_listings_gauge,
    db_write_duration_seconds,
    increment_errors,
    increment_listings_scraped,
    listings_scraped_total,
    observe_db_write,
    observe_scrape_duration,
    push_metrics,
    scrape_duration_seconds,
    scrape_errors_total,
    scraper_last_run_timestamp,
    set_active_listings,
)


def _get_counter_value(counter, labels: dict[str, str]) -> float:
    """Read the current value of a Counter metric for the given labels."""
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.labels == labels:
                return sample.value
    return 0.0


def _get_gauge_value(gauge, labels: dict[str, str]) -> float:
    """Read the current value of a Gauge metric for the given labels."""
    for metric in gauge.collect():
        for sample in metric.samples:
            if sample.labels == labels:
                return sample.value
    return 0.0


def _get_histogram_count(histogram, labels: dict[str, str]) -> float:
    """Read the _count sample of a Histogram for the given labels."""
    for metric in histogram.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count") and sample.labels == labels:
                return sample.value
    return 0.0


class TestMetrics:
    """Metric behaviour."""

    def test_listings_scraped_counter(self):
        """listings_scraped_total increments correctly."""
        increment_listings_scraped("otodom", "Warszawa", "apartment")
        value = _get_counter_value(
            listings_scraped_total,
            {"portal": "otodom", "city": "Warszawa", "type": "apartment"},
        )
        assert value == 1.0

        increment_listings_scraped("otodom", "Warszawa", "apartment")
        value = _get_counter_value(
            listings_scraped_total,
            {"portal": "otodom", "city": "Warszawa", "type": "apartment"},
        )
        assert value == 2.0

    def test_listings_scraped_different_labels(self):
        """Different label values create separate counters."""
        # Use unique label combos to avoid cross-test pollution
        increment_listings_scraped("otodom_labels", "Poznań", "house")
        increment_listings_scraped("gratka_labels", "Łódź", "flat")

        val_oto = _get_counter_value(
            listings_scraped_total,
            {"portal": "otodom_labels", "city": "Poznań", "type": "house"},
        )
        val_gratka = _get_counter_value(
            listings_scraped_total,
            {"portal": "gratka_labels", "city": "Łódź", "type": "flat"},
        )
        assert val_oto == 1.0
        assert val_gratka == 1.0

    def test_scrape_errors_counter(self):
        """scrape_errors_total increments correctly."""
        increment_errors("otodom", "timeout")
        value = _get_counter_value(
            scrape_errors_total,
            {"portal": "otodom", "error_type": "timeout"},
        )
        assert value == 1.0

    def test_scrape_duration_histogram(self):
        """scrape_duration_seconds records observations."""
        observe_scrape_duration("otodom", 30.5)
        count = _get_histogram_count(
            scrape_duration_seconds,
            {"portal": "otodom"},
        )
        assert count == 1.0

    def test_db_write_histogram(self):
        """db_write_duration_seconds records observations."""
        observe_db_write("insert_test", 0.05)
        count = _get_histogram_count(
            db_write_duration_seconds,
            {"operation": "insert_test"},
        )
        assert count == 1.0

    def test_active_listings_gauge(self):
        """active_listings_gauge sets correctly."""
        set_active_listings("otodom", 42)
        value = _get_gauge_value(
            active_listings_gauge,
            {"portal": "otodom"},
        )
        assert value == 42.0

        set_active_listings("otodom", 10)
        value = _get_gauge_value(
            active_listings_gauge,
            {"portal": "otodom"},
        )
        assert value == 10.0

    def test_scraper_last_run_timestamp_sets_label(self):
        """scraper_last_run_timestamp gauge accepts portal labels."""
        import time  # noqa: PLC0415

        now = time.time()
        scraper_last_run_timestamp.labels(portal="otodom").set(now)
        value = _get_gauge_value(
            scraper_last_run_timestamp,
            {"portal": "otodom"},
        )
        assert value >= now - 5  # Allow small clock skew

    def test_push_metrics_calls_push_to_gateway(self):
        """push_metrics delegates to prometheus_client.push_to_gateway."""
        with patch("scraper_base.metrics.push_to_gateway") as mock_push:
            push_metrics("http://pushgateway:9091", "test-portal")

        mock_push.assert_called_once_with(
            "http://pushgateway:9091",
            job="test-portal",
            registry=REGISTRY,
        )

    def test_push_metrics_default_registry(self):
        """push_metrics uses the default REGISTRY when none is given."""
        with patch("scraper_base.metrics.push_to_gateway") as mock_push:
            push_metrics("http://pushgateway:9091", "test-portal")

        _, kwargs = mock_push.call_args
        assert kwargs["registry"] is REGISTRY
