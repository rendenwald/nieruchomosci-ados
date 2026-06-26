"""Scrapy Items for Otodom scraper.

All fields match the Property table schema from specs/070-DATABASE.md.
"""

import scrapy


class OtodomItem(scrapy.Item):
    """Property listing item from Otodom."""

    # Required identifiers
    portal_source = scrapy.Field()  # Always "otodom"
    source_id = scrapy.Field()      # Otodom's internal ID
    source_url = scrapy.Field()     # Full URL to the listing

    # Core property data
    title = scrapy.Field()
    description = scrapy.Field()
    property_type = scrapy.Field()      # apartment, house, plot, commercial, garage, other
    auction_type = scrapy.Field()       # sell, rent
    market_type = scrapy.Field()        # primary, secondary
    offered_by = scrapy.Field()         # owner, developer, agency

    # Promotion
    is_promoted = scrapy.Field()
    promotion_expires_at = scrapy.Field()

    # Pricing
    price = scrapy.Field()              # Integer, PLN
    price_currency = scrapy.Field()     # "PLN"
    price_per_m2 = scrapy.Field()
    rent = scrapy.Field()               # For rent listings

    # Physical characteristics
    area = scrapy.Field()               # Float, m2
    plot_area = scrapy.Field()          # For plots/houses
    rooms = scrapy.Field()              # String (e.g., "2", "3.5", "4+")
    floor = scrapy.Field()              # String (e.g., "3", "parter", "poddasze")
    floors_total = scrapy.Field()
    year_built = scrapy.Field()
    condition = scrapy.Field()          # new, good, to_renovate, etc.
    heating = scrapy.Field()            # gas, electric, district, etc.
    extras = scrapy.Field()             # JSONB: parking, balcony, garden, etc.

    # Location
    province = scrapy.Field()
    city = scrapy.Field()
    district = scrapy.Field()
    street = scrapy.Field()
    latitude = scrapy.Field()
    longitude = scrapy.Field()

    # Agency info
    agency_name = scrapy.Field()
    agency_source_id = scrapy.Field()

    # Photos (list of URLs)
    photos = scrapy.Field()

    # Additional JSONB fields
    localization = scrapy.Field()       # Nearby POIs, transport, etc.
    building = scrapy.Field()           # Building details: type, material, etc.

    # Deduplication (set by pipeline)
    duplicate_group_id = scrapy.Field()
    is_canonical = scrapy.Field()

    # Timestamps
    scraped_at = scrapy.Field()
    last_seen_at = scrapy.Field()
    is_active = scrapy.Field()
    source_created_at = scrapy.Field()