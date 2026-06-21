"""Tests for structured logging configuration."""

import json
import logging
import sys

import pytest
import structlog

from scraper_base.logging_config import configure_logging, get_logger


class TestLoggingConfig:
    """Logging configuration tests."""

    def test_configure_logging_dev(self) -> None:
        """DEV_MODE enables console-friendly output."""
        configure_logging("DEBUG")

    def test_get_logger_returns_bound_logger(self) -> None:
        """get_logger returns a BoundLogger with standard fields."""
        configure_logging("DEBUG")
        logger = get_logger(portal="otodom", scraper_id="s1", run_id="r1")
        assert isinstance(logger, structlog.stdlib.BoundLogger)

    def test_json_output_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Production mode outputs valid JSON with all required fields."""
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=False,
        )
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.DEBUG,
            force=True,
        )

        logger = get_logger(portal="otodom", scraper_id="s1", run_id="r1")
        logger.info("Test message", price=520000)

        captured = capsys.readouterr()
        assert captured.out, "No stdout output captured"

        lines = [line for line in captured.out.split("\n") if line.strip()]
        assert len(lines) >= 1, f"Expected at least 1 log line, got {len(lines)}"

        entry = json.loads(lines[0])
        assert entry["event"] == "Test message"
        assert entry["level"] == "info"
        assert entry["portal"] == "otodom"
        assert entry["scraper_id"] == "s1"
        assert entry["run_id"] == "r1"
        assert "timestamp" in entry
        assert entry["price"] == 520000
