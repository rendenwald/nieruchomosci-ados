"""
City count response schema for the ``/api/v1/cities`` endpoint.

Provides ``CityCount`` which represents the number of active, canonical
properties in a given city.
"""

from pydantic import BaseModel


class CityCount(BaseModel):
    """A city with its associated property count.

    Attributes:
        city: The normalized city name.
        count: Number of active, canonical properties in this city.

    """

    city: str
    count: int
