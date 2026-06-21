"""Pydantic models for request/response serialization."""

from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.property import PropertyCard, SearchParams, SearchResponse

__all__ = [
    "ErrorResponse",
    "PaginatedResponse",
    "PropertyCard",
    "SearchParams",
    "SearchResponse",
]

