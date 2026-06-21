"""
Structured JSON logging configuration via structlog.

Provides a ``configure_logging()`` setup function and a ``get_logger()``
factory that returns a bound logger with consistent fields.
"""

import logging
import os
import sys
from typing import Any, cast

import structlog

_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_DEV_MODE = os.environ.get("DEV_MODE", "0").lower() in ("1", "true", "yes")


def configure_logging(level: str | None = None) -> None:
    """Configure structured JSON logging for the application.

    Args:
        level: Log level string (e.g. ``"DEBUG"``, ``"INFO"``). Falls back to
               the ``LOG_LEVEL`` env var, then ``"INFO"``.

    In development mode (``DEV_MODE=1``), a console-friendly coloured renderer
    is used instead of JSON. Production always uses JSON.

    """
    log_level = (level or _LOG_LEVEL).upper()

    shared_processors: list[structlog.typing.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if _DEV_MODE:
        # Console-friendly output for development
        renderer: Any = structlog.dev.ConsoleRenderer(
            sort_keys=False,
            colors=True,
        )
    else:
        # JSON output for production
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Also configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level, logging.INFO),
    )


def get_logger(
    portal: str = "unknown",
    scraper_id: str = "unknown",
    run_id: str = "unknown",
) -> structlog.stdlib.BoundLogger:
    """Return a bound logger pre-populated with standard fields.

    Args:
        portal: Portal source identifier (e.g. ``"otodom"``).
        scraper_id: Unique scraper instance identifier.
        run_id: Unique scraper run identifier.

    Returns:
        A ``BoundLogger`` with ``portal``, ``scraper_id``, and ``run_id``
        already bound.

    """
    return cast(
        structlog.stdlib.BoundLogger,
        structlog.get_logger().bind(
            portal=portal,
            scraper_id=scraper_id,
            run_id=run_id,
        ),
    )
