"""
Common Pydantic models for API responses.

Provides ``PaginatedResponse`` (generic) and ``ErrorResponse``.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        detail: Human-readable error description.
    """

    detail: str


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046 — Pydantic v2 needs Generic[T] for model_validate
    """Generic paginated response wrapper.

    Use via the ``SearchResponse`` type alias which binds ``T = PropertyCard``.

    Attributes:
        items: List of items for the current page.
        total: Total number of matching items across all pages.
        page: Current page number (1-indexed).
        limit: Number of items per page.
        total_pages: Total number of pages.
    """

    items: list[T]
    total: int
    page: int
    limit: int
    total_pages: int
