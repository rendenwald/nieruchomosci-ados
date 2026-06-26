"""Otodom Scrapy Pipeline.

Inherits from BasePipeline and implements Otodom-specific item mapping.
"""

from typing import Any

from scraper_base.pipeline import BasePipeline
from scraper_base.storage import MAX_PHOTOS_PER_PROPERTY


class OtodomPipeline(BasePipeline):
    """Scrapy pipeline for Otodom.pl listings.

    Processes OtodomItem objects, maps them to the Property schema,
    and persists via BasePipeline's upsert_property().
    """

    PORTAL_SOURCE = "otodom"

    # Selector fingerprints for validation (SHA256 of HTML snippets)
    # Update these when Otodom changes their HTML structure
    SELECTOR_FINGERPRINTS = {
        "listing_item": "",      # Filled after first successful scrape
        "detail_page": "",       # Filled after first successful scrape
        "pagination": "",        # Filled after first successful scrape
    }

    def item_to_data(self, item: dict[str, Any]) -> dict[str, Any]:
        """Convert OtodomItem to Property data dict.

        Args:
            item: Scrapy item dict from Otodom spider

        Returns:
            Dict matching Property model fields
        """
        data = dict(item)

        # Ensure portal_source is set
        data["portal_source"] = self.PORTAL_SOURCE

        # Normalize price to integer (remove spaces, currency symbols)
        if "price" in data and data["price"]:
            price_str = str(data["price"]).replace(" ", "").replace("PLN", "").replace("zł", "")
            try:
                data["price"] = int(float(price_str))
            except (ValueError, TypeError):
                data["price"] = None

        # Normalize price_per_m2
        if "price_per_m2" in data and data["price_per_m2"]:
            ppm_str = str(data["price_per_m2"]).replace(" ", "").replace("PLN", "").replace("zł", "").replace("/m²", "").replace("/m2", "")
            try:
                data["price_per_m2"] = int(float(ppm_str))
            except (ValueError, TypeError):
                data["price_per_m2"] = None

        # Normalize area to float
        if "area" in data and data["area"]:
            area_str = str(data["area"]).replace(" ", "").replace("m²", "").replace("m2", "").replace(",", ".")
            try:
                data["area"] = float(area_str)
            except (ValueError, TypeError):
                data["area"] = None

        # Normalize plot_area
        if "plot_area" in data and data["plot_area"]:
            pa_str = str(data["plot_area"]).replace(" ", "").replace("m²", "").replace("m2", "").replace(",", ".")
            try:
                data["plot_area"] = float(pa_str)
            except (ValueError, TypeError):
                data["plot_area"] = None

        # Normalize rooms to string (keep as-is, e.g., "2", "3.5", "4+")
        if "rooms" in data and data["rooms"]:
            data["rooms"] = str(data["rooms"]).strip()

        # Normalize floors_total
        if "floors_total" in data and data["floors_total"]:
            try:
                data["floors_total"] = int(data["floors_total"])
            except (ValueError, TypeError):
                data["floors_total"] = None

        # Normalize year_built
        if "year_built" in data and data["year_built"]:
            try:
                data["year_built"] = int(data["year_built"])
            except (ValueError, TypeError):
                data["year_built"] = None

        # Ensure photos is a list
        if "photos" in data and data["photos"]:
            if not isinstance(data["photos"], list):
                data["photos"] = [data["photos"]]
            # Filter out empty/invalid URLs
            data["photos"] = [p for p in data["photos"] if p and isinstance(p, str) and p.startswith("http")]
        else:
            data["photos"] = []

        # Ensure JSONB fields are dicts
        for field in ["extras", "localization", "building"]:
            if field in data and data[field] and not isinstance(data[field], dict):
                data[field] = {}
            elif field not in data:
                data[field] = {}

        # Set defaults
        data.setdefault("price_currency", "PLN")
        data.setdefault("is_active", True)
        data.setdefault("is_canonical", True)

        return data