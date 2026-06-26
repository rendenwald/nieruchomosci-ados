"""Shared fixtures and HTML samples for otodom-scrapper tests."""

from __future__ import annotations

from typing import Any

import pytest
from scrapy.http import HtmlResponse, Request

from otodom_scrapper.pipelines import OtodomPipeline

# ── Sample search results page ───────────────────────────────────────────
# Contains 3 listing cards and a pagination next-page link.
SAMPLE_SEARCH_HTML = """<!DOCTYPE html>
<html>
<body>
  <article data-cy="listing-item">
    <a data-cy="listing-item-link" href="/pl/oferta/mieszkanie-2-pokojowe-ABC123/"></a>
  </article>
  <article data-cy="listing-item">
    <a data-cy="listing-item-link" href="/pl/oferta/mieszkanie-3-pokojowe-DEF456/"></a>
  </article>
  <article data-cy="listing-item">
    <a data-cy="listing-item-link" href="/pl/oferta/mieszkanie-4-pokojowe-GHI789/"></a>
  </article>
  <a data-cy="pagination-next-page" href="/pl/oferty/sprzedaz/mieszkanie?page=2"></a>
</body>
</html>"""

# ── Sample detail page (full) ────────────────────────────────────────────
SAMPLE_DETAIL_HTML_FULL = """<!DOCTYPE html>
<html>
<body>
  <h1 data-cy="adPageAdTitle">Mieszkanie 2 pokoje, 58,5 m²</h1>
  <strong data-cy="adPageHeaderPrice">520 000 z\u0142</strong>

  <div aria-label="Cena za m²">
    <span aria-label="Cena za m²">8 888 z\u0142/m²</span>
  </div>

  <span aria-label="Powierzchnia">58,5 m²</span>
  <span aria-label="Liczba pokoi">3</span>
  <span aria-label="Pi\u0119tro">4</span>
  <span aria-label="Liczba pi\u0119ter">12</span>
  <span aria-label="Rok budowy">2020</span>
  <span aria-label="Stan wyko\u0144czenia">do zamieszkania</span>
  <span aria-label="Ogrzewanie">gazowe</span>

  <div data-cy="adPageAdDescription">
    Piękne mieszkanie w centrum miasta z widokiem na park.
    W pełni umeblowane z miejscem parkingowym.
  </div>

  <img data-cy="adPageGalleryImage" src="https://example.com/photo1.jpg" />
  <img data-cy="adPageGalleryImage" src="https://example.com/photo2.jpg" />
  <img data-cy="adPageGalleryImage" src="https://example.com/photo3.jpg" />

  <nav aria-label="Breadcrumb">
    <ol>
      <li><span>Otodom</span></li>
      <li><span>Sprzeda\u017c</span></li>
      <li><span>Warszawa</span></li>
      <li><span>\u015ar\u00f3dmie\u015bcie</span></li>
    </ol>
  </nav>

  <div data-map-lat="52.2297" data-map-lon="21.0122"></div>
  <div data-cy="adPageAgency">Super Agencja Nieruchomości</div>
  <meta itemprop="addressRegion" content="mazowieckie" />
  <meta itemprop="streetAddress" content="ul. Marszałkowska 100" />

  <span aria-label="Rynek">wtórny</span>
</body>
</html>"""

# ── Sample detail page (minimal — missing many fields) ───────────────────
SAMPLE_DETAIL_HTML_MINIMAL = """<!DOCTYPE html>
<html>
<body>
  <h1 data-cy="adPageAdTitle">Mieszkanie na sprzedaż</h1>

  <div data-cy="adPageAdDescription">
    Proste ogłoszenie bez szczegółów.
  </div>

  <nav aria-label="Breadcrumb">
    <ol>
      <li><span>Otodom</span></li>
      <li><span>Sprzeda\u017c</span></li>
      <li><span>Krak\u00f3w</span></li>
    </ol>
  </nav>
</body>
</html>"""

# ── Empty search results page ────────────────────────────────────────────
EMPTY_SEARCH_HTML = """<!DOCTYPE html>
<html>
<body>
  <div class="no-results">Brak ogłoszeń</div>
</body>
</html>"""


@pytest.fixture
def sample_search_html() -> str:
    """Fixture returning sample search results HTML."""
    return SAMPLE_SEARCH_HTML


@pytest.fixture
def sample_detail_html() -> str:
    """Fixture returning sample detail page HTML (full data)."""
    return SAMPLE_DETAIL_HTML_FULL


@pytest.fixture
def sample_detail_minimal_html() -> str:
    """Fixture returning sample detail page HTML (minimal data)."""
    return SAMPLE_DETAIL_HTML_MINIMAL


@pytest.fixture
def empty_results_html() -> str:
    """Fixture returning empty search results HTML."""
    return EMPTY_SEARCH_HTML


@pytest.fixture
def pipeline() -> OtodomPipeline:
    """Fixture providing an ``OtodomPipeline`` instance.

    Notes:
        The pipeline constructor does not connect to the database.
        Only ``item_to_data()`` is tested here (pure transformation).
    """
    return OtodomPipeline()


@pytest.fixture
def spider() -> Any:
    """Fixture providing an ``OtodomSpider`` instance.

    Returns:
        An initialized spider (no crawling performed).
    """
    from otodom_scrapper.spiders.otodom import OtodomSpider

    return OtodomSpider()


def make_response(body: str, url: str = "https://www.otodom.pl/pl/oferty/sprzedaz/mieszkanie") -> HtmlResponse:
    """Helper to create a mock ``HtmlResponse`` from a string body.

    Args:
        body: The HTML content.
        url: The request URL (defaults to search results URL).

    Returns:
        A ``HtmlResponse`` with the given body.
    """
    request = Request(url=url)
    return HtmlResponse(
        url=url,
        request=request,
        body=body.encode("utf-8"),
        encoding="utf-8",
    )
