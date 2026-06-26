"""Otodom.pl Scrapy spider.

Navigates Otodom search results pages, extracts listing detail URLs,
and parses individual listing pages into ``OtodomItem`` instances.
Uses Playwright for JavaScript rendering and stealth anti-detection.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from datetime import UTC
from typing import Any

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from otodom_scrapper.items import OtodomItem
from otodom_scrapper.stealth_utils import setup_page_stealth


class OtodomSpider(scrapy.Spider):
    """Spider for crawling otodom.pl real estate listings.

    Attributes:
        name: Spider identifier used by Scrapy.
        allowed_domains: Restrict crawling to otodom.pl.
        custom_settings: Scrapy settings overrides for this spider.
    """

    name = "otodom"
    allowed_domains = ["otodom.pl", "www.otodom.pl"]

    custom_settings: dict[bool | float | int | str | None, Any] | None = {
        "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        "PLAYWRIGHT_CONTEXT_NAME": "otodom",
    }

    def start_requests(self) -> Iterator[scrapy.Request]:
        """Yield initial search result page requests.

        Generates Playwright-enabled requests for both sell and rent
        listing categories, waiting for listing cards to render.
        """
        categories = [
            ("sprzedaz", "sell"),
            ("wynajem", "rent"),
        ]
        for category_path, auction_type in categories:
            url = f"https://www.otodom.pl/pl/oferty/{category_path}/mieszkanie"
            yield scrapy.Request(
                url=url,
                callback=self.parse_search_results,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod(
                            "wait_for_selector",
                            "css=article[data-cy='listing-item']",
                            timeout=15000,
                        ),
                    ],
                    "auction_type": auction_type,
                },
            )

    async def parse_search_results(self, response: Response) -> AsyncIterator[scrapy.Request]:
        """Parse search results page — extract listing URLs and pagination.

        Args:
            response: The Scrapy response from a search results page.

        Yields:
            Requests for detail pages and subsequent search result pages.
        """
        page = response.meta.get("playwright_page")
        if page is not None:
            try:
                await setup_page_stealth(page)
            finally:
                await page.close()

        auction_type = response.meta.get("auction_type", "sell")

        # Extract listing card URLs
        for listing in response.css("article[data-cy='listing-item']"):
            url = listing.css("a[data-cy='listing-item-link']::attr(href)").get()
            if url:
                yield scrapy.Request(
                    url=response.urljoin(url),
                    callback=self.parse_detail,
                    meta={
                        "playwright": True,
                        "playwright_include_page": True,
                        "auction_type": auction_type,
                    },
                )

        # Follow pagination
        next_page = response.css(
            "a[data-cy='pagination-next-page']::attr(href)",
        ).get()
        if next_page:
            yield scrapy.Request(
                url=response.urljoin(next_page),
                callback=self.parse_search_results,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "playwright_page_methods": [
                        PageMethod(
                            "wait_for_selector",
                            "css=article[data-cy='listing-item']",
                            timeout=15000,
                        ),
                    ],
                    "auction_type": auction_type,
                },
            )

    async def parse_detail(self, response: Response) -> AsyncIterator[OtodomItem]:
        """Parse a single listing detail page into an ``OtodomItem``.

        Extracts all available fields using CSS selectors targeting
        otodom.pl's known ``data-cy`` attributes.

        Args:
            response: The Scrapy response from a listing detail page.

        Yields:
            An ``OtodomItem`` with all extracted fields.
        """
        page = response.meta.get("playwright_page")
        if page is not None:
            try:
                await setup_page_stealth(page)
            finally:
                await page.close()

        item: dict[str, Any] = {}
        item["portal_source"] = "otodom"

        # ── Source identification ──────────────────────────────────────
        url = response.url
        item["source_url"] = url
        item["source_id"] = self._extract_source_id(url)

        # ── Title ───────────────────────────────────────────────────────
        item["title"] = response.css(
            "h1[data-cy='adPageAdTitle']::text",
        ).get()

        # ── Price ───────────────────────────────────────────────────────
        price_text = response.css(
            "strong[data-cy='adPageHeaderPrice']::text",
        ).get()
        item["price"] = price_text.strip() if price_text else None

        # ── Price per m² ────────────────────────────────────────────────
        ppm_text = response.css(
            "div[aria-label*='cena za']::text, "
            "span[aria-label*='Cena za']::text",
        ).get()
        item["price_per_m2"] = ppm_text.strip() if ppm_text else None

        # ── Area (surface) ──────────────────────────────────────────────
        area_text = response.css(
            "span[aria-label*='Powierzchnia']::text",
        ).get()
        item["area"] = area_text.strip() if area_text else None

        # ── Plot area ───────────────────────────────────────────────────
        plot_area_text = response.css(
            "span[aria-label*='Powierzchnia dzia']::text, "
            "div[aria-label*='Powierzchnia dzia']::text",
        ).get()
        item["plot_area"] = plot_area_text.strip() if plot_area_text else None

        # ── Rooms ───────────────────────────────────────────────────────
        rooms_text = response.css(
            "span[aria-label*='Liczba pokoi']::text",
        ).get()
        item["rooms"] = rooms_text.strip() if rooms_text else None

        # ── Floor / floors total ────────────────────────────────────────
        floor_text = response.css(
            "span[aria-label*='Pi\u0119tro']::text, "
            "span[aria-label*='Kondygnacja']::text",
        ).get()
        item["floor"] = floor_text.strip() if floor_text else None

        floors_total_text = response.css(
            "span[aria-label*='Liczba pi\u0119ter']::text, "
            "div[aria-label*='Liczba pi\u0119ter']::text",
        ).get()
        item["floors_total"] = floors_total_text.strip() if floors_total_text else None

        # ── Year built ──────────────────────────────────────────────────
        year_text = response.css(
            "span[aria-label*='Rok budowy']::text, "
            "div[aria-label*='Rok budowy']::text",
        ).get()
        item["year_built"] = year_text.strip() if year_text else None

        # ── Condition ───────────────────────────────────────────────────
        condition_text = response.css(
            "span[aria-label*='Stan wyko']::text, "
            "div[aria-label*='Stan']::text",
        ).get()
        item["condition"] = condition_text.strip() if condition_text else None

        # ── Heating ─────────────────────────────────────────────────────
        heating_text = response.css(
            "span[aria-label*='Ogrzewanie']::text, "
            "div[aria-label*='Ogrzewanie']::text",
        ).get()
        item["heating"] = heating_text.strip() if heating_text else None

        # ── Rent (for wynajem listings) ─────────────────────────────────
        rent_text = response.css(
            "strong[data-cy='adPageHeaderPrice']::text, "
            "div[aria-label*='Czynsz']::text",
        ).get()
        item["rent"] = rent_text.strip() if rent_text else None

        # ── Description ─────────────────────────────────────────────────
        description_parts = response.css(
            "div[data-cy='adPageAdDescription']::text",
        ).getall()
        item["description"] = (
            " ".join(p.strip() for p in description_parts if p.strip())
            if description_parts
            else None
        )

        # ── Photos ──────────────────────────────────────────────────────
        photo_urls = response.css(
            "img[data-cy='adPageGalleryImage']::attr(src)",
        ).getall()
        item["photos"] = list(dict.fromkeys(photo_urls)) if photo_urls else []

        # ── Property type ───────────────────────────────────────────────
        item["property_type"] = self._infer_property_type(url)

        # ── Auction type from meta ──────────────────────────────────────
        item["auction_type"] = response.meta.get("auction_type", "sell")

        # ── Market type (primary / secondary) ───────────────────────────
        market_text = response.css(
            "span[aria-label*='Rynek']::text, "
            "div[aria-label*='Rynek']::text",
        ).get()
        if market_text:
            raw = market_text.strip().lower()
            if "pierwotny" in raw or "deweloper" in raw or "primary" in raw:
                item["market_type"] = "primary"
            else:
                item["market_type"] = "secondary"

        # ── Agency ──────────────────────────────────────────────────────
        agency_name = response.css(
            "a[data-cy='agent-box-link']::text, "
            "div[data-cy='adPageAgency']::text",
        ).get()
        item["agency_name"] = agency_name.strip() if agency_name else None

        agency_href = response.css(
            "a[data-cy='agent-box-link']::attr(href)",
        ).get()
        if agency_href:
            match = re.search(r"/([A-Z0-9-]+)/?$", agency_href)
            item["agency_source_id"] = match.group(1) if match else None

        # ── Location from breadcrumbs ───────────────────────────────────
        self._extract_location(response, item)

        # ── Coordinates from map data attributes ────────────────────────
        lat = response.css(
            "div[data-map-lat]::attr(data-map-lat), "
            "div[data-lat]::attr(data-lat), "
            "meta[itemprop='latitude']::attr(content)",
        ).get()
        lon = response.css(
            "div[data-map-lon]::attr(data-map-lon), "
            "div[data-lng]::attr(data-lng), "
            "meta[itemprop='longitude']::attr(content)",
        ).get()
        if lat:
            try:
                item["latitude"] = float(lat)
            except (ValueError, TypeError):
                pass
        if lon:
            try:
                item["longitude"] = float(lon)
            except (ValueError, TypeError):
                pass

        # ── Promotion status ────────────────────────────────────────────
        promoted = response.css("[data-cy='promoted-badge'], .promoted-badge").get()
        item["is_promoted"] = promoted is not None

        # ── Scraped at timestamp ────────────────────────────────────────
        from datetime import datetime

        item["scraped_at"] = datetime.now(UTC).isoformat()
        item["last_seen_at"] = item["scraped_at"]
        item["is_active"] = True

        # ── Build final item ────────────────────────────────────────────
        otodom_item = OtodomItem(item)
        yield otodom_item

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_source_id(url: str) -> str | None:
        """Extract the unique listing identifier from an Otodom URL.

        Otodom URLs contain either a 32-character hex UUID or a shorter
        alphanumeric ID in the path or the last path segment.

        Args:
            url: The full listing URL.

        Returns:
            The extracted source ID, or ``None`` if no pattern matches.
        """
        # UUID pattern: 32 hex characters
        match = re.search(r"/([a-f0-9]{32})(?:\?|/|$)", url)
        if match:
            return match.group(1)

        # Numeric ID pattern: /ID/ segment (5+ digits)
        match = re.search(r"/(\d{5,})(?:\?|/|$)", url)
        if match:
            return match.group(1)

        # HTML file pattern: last segment before .html extension
        match = re.search(r"/([^/]+?)\.html$", url)
        if match:
            return match.group(1)

        # Fallback: alphanumeric ID in last path segment after /oferta/
        # e.g., .../oferta/mieszkanie-2-pokojowe-ABC123
        match = re.search(r"/oferta/[^/]+-([A-Za-z0-9_-]{3,})(?:\?|/|$)", url)
        if match:
            return match.group(1)

        # Last resort: last non-empty path segment
        match = re.search(r"/([^/]+?)(?:\?|/|$)", url)
        if match:
            candidate = match.group(1)
            # Avoid matching generic path segments like "pl", "oferty", "sprzedaz", etc.
            if candidate and not any(
                generic in candidate
                for generic in [
                    "pl", "oferty", "sprzedaz", "wynajem",
                    "mieszkanie", "dom", "dzialka", "lokal", "garaz", "other",
                ]
            ):
                return candidate

        return None

    @staticmethod
    def _infer_property_type(url: str) -> str | None:
        """Infer the property type from the URL path.

        Extracts the path component to avoid false matches on the
        domain name (e.g. ``"otodom"`` contains ``"dom"``).

        Args:
            url: The listing URL.

        Returns:
            The property type string, or ``None`` if unknown.
        """
        path = url.split("?")[0]  # Strip query parameters
        if "/mieszkanie" in path:
            return "apartment"
        if "/dzialka" in path or "/dzia\u0142ka" in path:
            return "plot"
        if "/lokal" in path:
            return "commercial"
        if "/garaz" in path or "/gara\u017c" in path:
            return "garage"
        if "/dom" in path:
            return "house"
        return None

    @staticmethod
    def _extract_location(response: Response, item: dict[str, Any]) -> None:
        """Extract location fields from breadcrumbs and page content.

        Args:
            response: The Scrapy response.
            item: The item dict to populate with location data.
        """
        # Breadcrumb items
        breadcrumbs = response.css(
            "nav[aria-label='Breadcrumb'] li span::text, "
            "li[data-cy='breadcrumb-item'] span::text, "
            "ol[aria-label='Breadcrumb'] li span::text",
        ).getall()
        breadcrumbs = [b.strip() for b in breadcrumbs if b.strip()]

        # Typical breadcrumb structure:
        # [0] Strona główna / Otodom
        # [1] Sprzedaż / Wynajem
        # [2] City name
        # [3] District (optional)
        if len(breadcrumbs) >= 3:
            item["city"] = breadcrumbs[2]
        if len(breadcrumbs) >= 4:
            item["district"] = breadcrumbs[3]

        # Province: try to extract from meta or data attributes
        province = response.css(
            "meta[itemprop='addressRegion']::attr(content), "
            "span[itemprop='addressRegion']::text",
        ).get()
        if province:
            item["province"] = province.strip()

        # Street address
        street = response.css(
            "meta[itemprop='streetAddress']::attr(content), "
            "span[itemprop='streetAddress']::text",
        ).get()
        if street:
            item["street"] = street.strip()
