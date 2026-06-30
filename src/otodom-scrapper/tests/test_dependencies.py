"""
Dependency regression tests for the otodom-scrapper.

Verifies that all runtime dependencies import correctly.
This guards against issues like missing transitive dependencies
(e.g. ``pkg_resources`` from ``setuptools`` required by ``playwright_stealth``).
"""


class TestDependencyImports:
    """DEP-*: Verify that all key dependencies import without errors."""

    def test_dep1_playwright_stealth_imports(self) -> None:
        """DEP-1: ``playwright_stealth`` imports cleanly.

        Regression test: ``playwright_stealth.stealth`` uses ``import pkg_resources``
        at module level, which requires ``setuptools`` to be installed as a
        runtime dependency. This test fails if ``setuptools`` is missing.
        """
        # This import must succeed without raising ModuleNotFoundError
        from playwright_stealth import stealth_async, stealth_sync  # noqa: F401

    def test_dep2_scrapy_imports(self) -> None:
        """DEP-2: Scrapy imports cleanly."""
        import scrapy  # noqa: F401

    def test_dep3_scraper_base_imports(self) -> None:
        """DEP-3: scrapper-base components import cleanly."""
        from scraper_base.pipeline import BasePipeline  # noqa: F401
        from scraper_base.storage import MinioStorageClient  # noqa: F401
        from scraper_base.models import Property  # noqa: F401
