"""Tests using the saved otodom.pl HTML fixture file.

These tests load the realistic HTML file from
``tests/otodom-search-results/search-results-with-photos.html``
which represents a real otodom.pl search results page with photos.
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


class TestRealSearchResults:
    """Test spider parsing using the saved otodom.pl HTML fixture.

    The fixture file contains 6 listing cards with real-world structure:
    photo ``<img>`` tags, ``data-cy`` attributes, price/location text,
    and pagination controls.
    """

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_extracts_all_listing_urls(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        search_results_with_photos_html: str,
    ) -> None:
        """All 6 listing card URLs are extracted from the fixture."""
        response = make_response(search_results_with_photos_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        detail_requests = [
            r for r in results
            if isinstance(r, Request) and "oferta" in r.url
        ]
        assert len(detail_requests) == 6

        # Verify expected listing IDs are found
        urls = [r.url for r in detail_requests]
        assert any("ABC123" in u for u in urls)
        assert any("DEF456" in u for u in urls)
        assert any("GHI789" in u for u in urls)
        assert any("JKL012" in u for u in urls)
        assert any("MNO345" in u for u in urls)
        assert any("PQR678" in u for u in urls)

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_pagination_extracted(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        search_results_with_photos_html: str,
    ) -> None:
        """Pagination next-page link is extracted from the fixture."""
        response = make_response(search_results_with_photos_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        pagination_requests = [
            r for r in results
            if isinstance(r, Request) and "page=2" in r.url
        ]
        assert len(pagination_requests) == 1

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_all_detail_requests_have_playwright(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        search_results_with_photos_html: str,
    ) -> None:
        """Every detail request from fixture carries playwright=True."""
        response = make_response(search_results_with_photos_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        detail_requests = [
            r for r in results
            if isinstance(r, Request) and r.callback.__name__ == "parse_detail"
        ]
        assert len(detail_requests) == 6
        for req in detail_requests:
            assert req.meta.get("playwright") is True

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_auction_type_propagated(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        search_results_with_photos_html: str,
    ) -> None:
        """Auction_type from initial meta is carried to all child requests."""
        response = make_response(
            search_results_with_photos_html,
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


class TestRealFixturePhotoDetection:
    """Test that photo-related HTML structure is correctly parsed.

    The fixture contains ``<img>`` tags inside listing cards. While the
    spider's ``parse_search_results`` method doesn't extract photos from
    search results (that happens at detail level), we verify that:
    - Listing cards with photos are still parsed as valid listings
    - Photo URLs in search results don't interfere with URL extraction
    """

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_listing_with_images_parsed_correctly(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
        search_results_with_photos_html: str,
    ) -> None:
        """Listing cards containing <img> tags are parsed correctly,
        extracting both the listing URL and ignoring image elements."""
        response = make_response(search_results_with_photos_html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)

        # All 6 listings should be found even with photos present
        detail_requests = [
            r for r in results
            if isinstance(r, Request) and r.callback.__name__ == "parse_detail"
        ]
        assert len(detail_requests) == 6

        # URLs should point to offer pages, not image sources
        for req in detail_requests:
            assert "/pl/oferta/" in req.url
            assert "ireland.apollo.olxcdn.com" not in req.url


class TestRealFixtureEdgeCases:
    """Edge case tests using the real fixture.

    Verifies that the spider handles:
    - Missing ``data-cy`` attributes gracefully
    - Empty search results (no listing items)
    - Listing cards without photo images
    """

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_no_listing_items_returns_empty(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
    ) -> None:
        """A page with zero listing-item articles yields no results."""
        html = """<!DOCTYPE html>
        <html><body>
        <div class="no-results">Brak ogłoszeń</div>
        </body></html>"""
        response = make_response(html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)
        assert len(results) == 0

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_listing_without_photo_link(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
    ) -> None:
        """A listing card without an <img> tag is still parsed."""
        html = """<!DOCTYPE html>
        <html><body>
        <article data-cy="listing-item">
          <a data-cy="listing-item-link" href="/pl/oferta/mieszkanie-bez-zdjec/">
            Mieszkanie bez zdjęć
          </a>
        </article>
        </body></html>"""
        response = make_response(html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)
        detail_requests = [
            r for r in results
            if isinstance(r, Request) and "mieszkanie-bez-zdjec" in r.url
        ]
        assert len(detail_requests) == 1

    @patch("otodom_scrapper.spiders.otodom.setup_page_stealth", new_callable=AsyncMock)
    async def test_missing_data_cy_attributes(
        self,
        mock_stealth: AsyncMock,
        spider: OtodomSpider,
    ) -> None:
        """Listing cards without required data-cy attributes are skipped."""
        html = """<!DOCTYPE html>
        <html><body>
        <article>
          <a href="/pl/oferta/bez-data-cy/">No data-cy</a>
        </article>
        </body></html>"""
        response = make_response(html)
        results: list[Any] = []
        async for result in spider.parse_search_results(response):
            results.append(result)
        # Should yield no results since data-cy attributes are missing
        assert len(results) == 0


class TestRealFixtureSourceIdExtraction:
    """Test source_id extraction using fixture listing URLs."""

    def test_source_id_from_fixture_urls(self, spider: OtodomSpider) -> None:
        """Verify source_id extraction from fixture URL patterns."""
        test_cases = [
            ("/pl/oferta/mieszkanie-2-pokojowe-centrum-ABC123/", "ABC123"),
            ("/pl/oferta/mieszkanie-3-pokojowe-mokotow-DEF456/", "DEF456"),
            ("/pl/oferta/mieszkanie-4-pokojowe-wola-GHI789/", "GHI789"),
            ("/pl/oferta/mieszkanie-2-pokojowe-praga-JKL012/", "JKL012"),
            ("/pl/oferta/mieszkanie-3-pokojowe-ursynow-MNO345/", "MNO345"),
            ("/pl/oferta/mieszkanie-1-pokojowe-bemowo-PQR678/", "PQR678"),
        ]
        for url, expected_id in test_cases:
            source_id = spider._extract_source_id(f"https://otodom.pl{url}")
            assert source_id == expected_id, f"Failed for {url}: got {source_id}"
