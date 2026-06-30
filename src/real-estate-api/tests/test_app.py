"""
App-level tests: module imports, ASGI entry point, and app configuration.

Verifies that ``app.main`` exports the ``app`` attribute expected by
ASGI servers (uvicorn, gunicorn, etc.).
"""

from fastapi import FastAPI


class TestAppEntryPoint:
    """Tests that ``app.main`` exports the correct ASGI entry point.

    Uvicorn expects ``app.main:app`` — the module must have a module-level
    ``app`` attribute that is a FastAPI (ASGI) instance.
    """

    def test_app_attr_exists(self) -> None:
        """The module ``app.main`` exports an ``app`` attribute."""
        from app.main import app  # type: ignore[attr-defined]

        assert app is not None

    def test_app_attr_is_fastapi_instance(self) -> None:
        """The ``app`` attribute is a ``FastAPI`` instance."""
        from app.main import app  # type: ignore[attr-defined]

        assert isinstance(app, FastAPI)

    def test_app_title_matches_expected(self) -> None:
        """The app has the expected title."""
        from app.main import app  # type: ignore[attr-defined]

        assert app.title == "Real Estate Aggregation API"

    def test_app_router_count_minimum(self) -> None:
        """App has a reasonable number of routes (>= 9 routes expected)."""
        from app.main import app  # type: ignore[attr-defined]

        # Accessing the raw list of routes. Iteration may trigger large
        # object traversal in FastAPI 0.138+, so we only check the count.
        count = len(app.router.routes)
        assert count >= 9, f"Expected >= 9 routes, got {count}"
