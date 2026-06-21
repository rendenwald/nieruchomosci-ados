"""
Pydantic models for property-related request/response schemas.

Provides ``PropertyCard`` (listing view), ``SearchParams`` (request validation),
and ``SearchResponse`` (paginated response).
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import PaginatedResponse

# Pattern for sort parameter: ``field:direction``
_SORT_PATTERN = re.compile(r"^[a-zA-Z_]+:(asc|desc)$")


class PropertyCard(BaseModel):
    """Property data for list view (subset of full Property model).

    Attributes:
        id: Unique property identifier.
        title: Property listing title.
        property_type: Type of property (apartment, house, etc.).
        price: Total price in the smallest currency unit.
        price_currency: ISO 4217 currency code (e.g. "PLN").
        price_per_m2: Price per square meter.
        area: Total area in square meters.
        rooms: Number of rooms as a string (e.g. "2", "3+").
        city: City name.
        district: District or neighbourhood.
        province: Voivodeship / province.
        latitude: Geographic latitude.
        longitude: Geographic longitude.
        agency_name: Name of the listing agency.
        photos: List of photo URLs.
        source_url: Original listing URL.
        portal_source: Source portal identifier (e.g. "otodom").
        created_at: When the property was first scraped.
    """

    id: int
    title: str | None = None
    property_type: str | None = None
    price: int | None = None
    price_currency: str | None = None
    price_per_m2: int | None = None
    area: float | None = None
    rooms: str | None = None
    city: str | None = None
    district: str | None = None
    province: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    agency_name: str | None = None
    photos: list[str] | None = None
    source_url: str | None = None
    portal_source: str | None = None
    created_at: datetime | None = None


class SearchParams(BaseModel):
    """Query parameters for the properties search endpoint.

    All filter parameters are optional. Validation is applied to enforce
    constraints (non-negative prices/areas, bounded pagination, sort format).
    """

    city: str | None = None
    property_type: str | None = None
    auction_type: str | None = None
    market_type: str | None = None
    price_min: int | None = Field(None, ge=0)
    price_max: int | None = Field(None, ge=0)
    area_min: float | None = Field(None, ge=0)
    area_max: float | None = Field(None, ge=0)
    rooms: str | None = None
    sort_by: str | None = "last_seen_at:desc"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("sort_by")
    @classmethod
    def validate_sort_format(cls, v: str | None) -> str | None:
        """Validate the sort parameter matches ``field:direction`` format.

        Args:
            v: The sort string to validate.

        Returns:
            The validated sort string, or ``"last_seen_at:desc"`` if ``None``.

        Raises:
            ValueError: If the format does not match ``field:direction``.

        """
        if v is None:
            return "last_seen_at:desc"
        if not _SORT_PATTERN.match(v):
            msg = f"Invalid sort format: '{v}'. Expected 'field:asc' or 'field:desc'."
            raise ValueError(msg)
        return v


SearchResponse = PaginatedResponse[PropertyCard]
"""Type alias for the paginated property search response."""
