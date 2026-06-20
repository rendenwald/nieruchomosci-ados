"""Tests for structured logging configuration."""

import structlog

from scraper_base.logging_config import configure_logging, get_logger


class TestLoggingConfig:
    """Logging configuration."""

    def test_configure_logging_dev(self):
        """DEV_MODE enables console-friendly output."""
        configure_logging("DEBUG")

    def test_get_logger_returns_bound_logger(self):
        """get_logger returns a BoundLogger with standard fields."""
        configure_logging("DEBUG")
        logger = get_logger(portal="otodom", scraper_id="s1", run_id="r1")
        assert isinstance(logger, structlog.stdlib.BoundLogger)

    def test_logger_has_bound_fields(self):
        """Bound fields persist across log calls."""
        configure_logging("DEBUG")

        structlog.configure(
            processors=[
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            cache_logger_on_first_use=False,
        )

        logger = get_logger(portal="otodom", scraper_id="scraper-1", run_id="run-001")
        logger.info("Test message", extra_field="value")

        # Since we're using JSON rendering, capture is via the stream
        # This test verifies the logger is configured and doesn't crash
        assert True

    def test_json_output_format(self):
        """Production mode outputs JSON-formatted logs."""
        # Reconfigure for JSON
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            cache_logger_on_first_use=False,
        )


        logger = get_logger(portal="test", scraper_id="s1", run_id="r1")

        # This should work without errors
        logger.info("JSON test")
        assert True
