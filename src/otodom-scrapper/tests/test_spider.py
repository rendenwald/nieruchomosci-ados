"""Tests for ``OtodomSpider`` parsing logic.

All tests use inline HTML fixtures — no network requests are made.
Spider methods are tested by constructing ``HtmlResponse`` objects
and iterating the async generators.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from scrapy.http import Request

from otodom_scrapper.spiders.otodom import OtodomSpider

from .conftest import make_response


@pytest.fixture
def spider() -> OtodomSpider:
    """Fixture providing an ``OtodomSpider`` instance."""
    return OtodomSpider()


# ── Spider identity ──────────────────────────────────────────────────────


class TestSpiderIdentity:
    """TC-S6, TC-S7: Spider configuration."""

    def test_spider_name(self, spider: OtodomSpider) -> None:
        """TC-S6: Spider name is 'otodom'."""
        assert spider.name == "otodom"

    def test_allowed_domains(self, spider: OtodomSpider) -> None:
        """TC-S7: Allowed domains include otodom.pl."""
        assert "otodom.pl" in spider.allowed_domains

    def test_custom_settings(self, spider: OtodomSpider) -> None:
        """Custom settings include Playwright configuration."""
        assert spider.custom_settings["PLAYWRIGHT_LAUNCH_OPTIONS"] == {"headless": True}
        assert spider.custom_settings["PLAYWRIGHT_CONTEXT_NAME"] == "otodom"


# ── Start requests ───────────────────────────────────────────────────────


class TestStartRequests:
    """TC-S8: Start requests include sell listing URLs."""

    def test_start_requests_sell(self, spider: OtodomSpider) -> None:
        """Start request URLs contain 'sprzedaz/mieszkanie'."""
        requests = list(spider.start_requests())
        assert len(requests) >= 1
        urls = [r.url for r in requests]
        assert any("sprzedaz" in url for url in urls)

    def test_start_requests_rent(self, spider: OtodomSpider) -> None:
        """Start request URLs contain 'wynajem/mieszkanie'."""
        requests = list(spider.start_requests())
        urls = [r.url for r in requests]
        assert any("wynajem" in url for url in urls)

    def test_start_requests_playwright_meta(self, spider: OtodomSpider) -> None:
        """Start requests have playwright=True in meta."""
        requests = list(spider.start_requests())
        for req in requests:
            assert req.meta.get("playwright") is True

    def test_start_requests_auction_type(self, spider: OtodomSpider) -> None:
        """Start requests carry auction_type in meta."""
        requests = list(spider.start_requests())
        # Check that sprzedaz maps to sell, wynajem maps to rent
        for req in requests:
            if "sprzedaz" in req.url:
                assert req.meta.get("auction_type") == "sell"
            elif "wynajem" in req.url:
                assert req.meta.get("auction_type") == "rent"


# ── Search results parsing ───────────────────────────────────────────────


class TestParseSearchResults:
    """TC-S1, TC-S2, TC-S5: Search results page parsing."""

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_parse_listing_cards(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_search_html: str,
    ) -> None:
        """TC-S1: Listing card URLs extracted from search results."""
        response = make_response(sample_search_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        # Should yield 3 detail page requests
        detail_requests = [r for r in results if isinstance(r, Request) and "oferta" in r.url]
        assert len(detail_requests) == 3
        assert any("ABC123" in r.url for r in detail_requests)
        assert any("DEF456" in r.url for r in detail_requests)
        assert any("GHI789" in r.url for r in detail_requests)

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_pagination(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_search_html: str,
    ) -> None:
        """TC-S2: Next page URL extracted."""
        response = make_response(sample_search_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        # Should yield a pagination request
        pagination_requests = [
            r for r in results
            if isinstance(r, Request) and "page=2" in r.url
        ]
        assert len(pagination_requests) == 1

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_empty_results(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        empty_results_html: str,
    ) -> None:
        """TC-S5: Empty results page yields no items, no crash."""
        response = make_response(empty_results_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        assert len(results) == 0

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_detail_requests_have_playwright(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_search_html: str,
    ) -> None:
        """Detail page requests have playwright=True."""
        response = make_response(sample_search_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        detail_requests = [
            r for r in results
            if isinstance(r, Request) and r.callback.__name__ == "parse_detail"
        ]
        for req in detail_requests:
            assert req.meta.get("playwright") is True

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_auction_type_carried_forward(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_search_html: str,
    ) -> None:
        """Auction type from initial request is carried to detail requests."""
        response = make_response(
            sample_search_html,
            url="https://www.otodom.pl/pl/oferty/sprzedaz/mieszkanie",
        )
        response.meta["auction_type"] = "sell"
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        detail_requests = [
            r for r in results
            if isinstance(r, Request) and r.callback.__name__ == "parse_detail"
        ]
        for req in detail_requests:
            assert req.meta.get("auction_type") == "sell"


# ── Detail page parsing ──────────────────────────────────────────────────


class TestParseDetail:
    """TC-S3, TC-S4: Detail page parsing."""

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_full_detail(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_detail_html: str,
    ) -> None:
        """TC-S3: Full detail page yields an item with all fields."""
        url = "https://www.otodom.pl/pl/oferta/mieszkanie-2-pokojowe-ABC123"
        response = make_response(sample_detail_html, url=url)
        response.meta["auction_type"] = "sell"

        items: list[Any] = []
        async for item in spider.parse_detail(response):
            items.append(item)

        assert len(items) == 1
        item = dict(items[0])

        # Core fields
        assert item["portal_source"] == "otodom"
        assert item["title"] == "Mieszkanie 2 pokoje, 58,5 m²"
        assert item["price"] == "520 000 zł"
        assert item["price_per_m2"] == "8 888 zł/m²"
        assert item["area"] == "58,5 m²"
        assert item["rooms"] == "3"
        assert item["floor"] == "4"
        assert item["floors_total"] == "12"
        assert item["year_built"] == "2020"
        assert item["condition"] == "do zamieszkania"
        assert item["heating"] == "gazowe"
        assert "Piękne mieszkanie" in item["description"]

        # Photos
        assert len(item["photos"]) == 3
        assert "photo1.jpg" in item["photos"][0]

        # Location
        assert item["city"] == "Warszawa"
        assert item["district"] == "Śródmieście"
        assert item["province"] == "mazowieckie"
        assert item["street"] == "ul. Marszałkowska 100"

        # Coordinates
        assert item["latitude"] == 52.2297
        assert item["longitude"] == 21.0122

        # Property type
        assert item["property_type"] == "apartment"
        assert item["auction_type"] == "sell"
        assert item["market_type"] == "secondary"

        # Agency
        assert item["agency_name"] == "Super Agencja Nieruchomości"

        # Source
        assert item["source_id"] == "ABC123"
        assert item["source_url"] == url

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_minimal_detail(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_detail_minimal_html: str,
    ) -> None:
        """TC-S4: Minimal detail page yields item with defaults."""
        url = "https://www.otodom.pl/pl/oferta/minimal-123"
        response = make_response(sample_detail_minimal_html, url=url)
        response.meta["auction_type"] = "sell"

        items: list[Any] = []
        async for item in spider.parse_detail(response):
            items.append(item)

        assert len(items) == 1
        item = dict(items[0])

        # Fields present
        assert item["title"] == "Mieszkanie na sprzedaż"
        assert item["city"] == "Kraków"
        assert item["source_id"] is not None

        # Fields that should be None/default
        assert item["price"] is None
        assert item["area"] is None
        assert item["rooms"] is None
        assert item["photos"] == []
        assert item.get("latitude") is None
        assert item.get("longitude") is None
        assert item.get("property_type") is None  # "minimal" not in URL patterns

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_rent_listing(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_detail_html: str,
    ) -> None:
        """Rent listing gets auction_type=rent."""
        url = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/test-rent-1"
        response = make_response(sample_detail_html, url=url)
        response.meta["auction_type"] = "rent"

        items: list[Any] = []
        async for item in spider.parse_detail(response):
            items.append(item)

        assert len(items) == 1
        item = dict(items[0])
        assert item["auction_type"] == "rent"


# ── Source ID extraction ─────────────────────────────────────────────────


class TestSourceIdExtraction:
    """Verify source_id extraction from various URL patterns."""

    def test_uuid_pattern(self, spider: OtodomSpider) -> None:
        """32-char hex UUID in URL."""
        source_id = spider._extract_source_id(
            "https://www.otodom.pl/pl/oferta/550a33a0b1c2d3e4f5a6b7c8d9e0f123"
        )
        assert source_id == "550a33a0b1c2d3e4f5a6b7c8d9e0f123"

    def test_long_numeric_id(self, spider: OtodomSpider) -> None:
        """Long numeric ID in URL."""
        source_id = spider._extract_source_id(
            "https://www.otodom.pl/pl/oferta/123456789"
        )
        assert source_id == "123456789"

    def test_html_extension(self, spider: OtodomSpider) -> None:
        """ID from .html URL."""
        source_id = spider._extract_source_id(
            "https://www.otodom.pl/pl/oferta/mieszkanie-12345.html"
        )
        assert source_id == "mieszkanie-12345"

    def test_no_match(self, spider: OtodomSpider) -> None:
        """No recognizable ID returns None."""
        source_id = spider._extract_source_id("https://www.otodom.pl/")
        assert source_id is None


# ── Property type inference ──────────────────────────────────────────────


class TestPropertyTypeInference:
    """Verify property type inference from URL."""

    def test_apartment(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/mieszkanie/123") == "apartment"

    def test_house(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/dom/123") == "house"

    def test_plot(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/dzialka/123") == "plot"

    def test_commercial(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/lokal/123") == "commercial"

    def test_garage(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/garaz/123") == "garage"

    def test_unknown(self, spider: OtodomSpider) -> None:
        assert spider._infer_property_type("https://otodom.pl/other") is None


# ── Playwright page handling ─────────────────────────────────────────────


class TestPlaywrightPageHandling:
    """Verify Playwright page is properly closed after use."""

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_playwright_page_closed(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        sample_detail_html: str,
    ) -> None:
        """Playwright page.close() is called when page is present.

        We simulate having a playwright_page by patching the meta.
        """
        url = "https://www.otodom.pl/pl/oferta/test/123"
        response = make_response(sample_detail_html, url=url)
        mock_page = AsyncMock()
        response.meta["playwright_page"] = mock_page
        response.meta["auction_type"] = "sell"

        async for _ in spider.parse_detail(response):
            pass

        # stealth was called
        mock_stealth.assert_awaited_once_with(mock_page)
        # page was closed
        mock_page.close.assert_awaited_once()
