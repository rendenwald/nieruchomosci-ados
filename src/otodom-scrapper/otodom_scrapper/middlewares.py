"""Otodom Scrapy downloader middlewares.

Provides stealth header injection for Playwright-enabled requests.
"""

from __future__ import annotations

from typing import Any

from scrapy import Spider
from scrapy.http import Response


class OtodomDownloaderMiddleware:
    """Middleware that ensures stealth headers are applied.

    For Playwright-enabled requests, the ``stealth_utils.setup_page_stealth()``
    function handles header injection at the page level. This middleware exists
    primarily as a Scrapy requirement and can be extended for non-Playwright
    request header enrichment in the future.
    """

    @staticmethod
    async def process_response(
        request: Any,
        response: Response,
        spider: Spider,
    ) -> Response:
        """Pass through the response unchanged.

        Args:
            request: The original request.
            response: The received response.
            spider: The active spider.

        Returns:
            The unmodified response for further processing.
        """
        return response
