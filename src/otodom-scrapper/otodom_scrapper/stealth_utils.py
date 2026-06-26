"""Playwright stealth utilities for Otodom scraper.

Provides anti-detection measures: random user agents, viewport randomization,
behavioral simulation, and request interception.
"""

import random
from typing import Any
from playwright.async_api import BrowserContext, Page
from playwright_stealth import stealth_async


# Common desktop user agents (Chrome on Windows/Linux/macOS)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# Common viewport sizes
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
]


async def create_stealth_context(browser: Any, **kwargs: Any) -> BrowserContext:
    """Create a new browser context with stealth configuration.

    Args:
        browser: Playwright browser instance
        **kwargs: Additional context options

    Returns:
        Configured BrowserContext with stealth applied
    """
    # Randomize user agent and viewport
    user_agent = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)

    context = await browser.new_context(
        user_agent=user_agent,
        viewport=viewport,
        locale="pl-PL",
        timezone_id="Europe/Warsaw",
        color_scheme="light",
        reduced_motion="reduce",
        forced_colors="none",
        **kwargs,
    )

    # Apply playwright-stealth
    await stealth_async(context)

    # Additional anti-detection measures
    await _add_stealth_scripts(context)

    return context


async def _add_stealth_scripts(context: BrowserContext) -> None:
    """Inject additional stealth scripts into the context."""
    # Override navigator properties
    await context.add_init_script("""
        // Hide webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });

        // Mock plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ],
        });

        // Mock languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['pl-PL', 'pl', 'en-US', 'en'],
        });

        // Mock hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8,
        });

        // Mock device memory
        Object.defineProperty(navigator, 'deviceMemory', {
            get: () => 8,
        });

        // Mock platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32',
        });
    """)


async def setup_page_stealth(page: Page) -> None:
    """Apply stealth measures to a specific page.

    Args:
        page: Playwright Page instance
    """
    # Random delay before navigation
    await page.wait_for_timeout(random.randint(500, 1500))

    # Set extra headers
    await page.set_extra_http_headers({
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })


async def random_delay(min_ms: int = 1000, max_ms: int = 3000) -> None:
    """Sleep for a random duration to simulate human behavior.

    Args:
        min_ms: Minimum delay in milliseconds
        max_ms: Maximum delay in milliseconds
    """
    import asyncio
    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)


async def simulate_human_behavior(page: Page) -> None:
    """Simulate human-like interactions on the page.

    Args:
        page: Playwright Page instance
    """
    # Random mouse movements
    for _ in range(random.randint(2, 5)):
        x = random.randint(100, 800)
        y = random.randint(100, 600)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await random_delay(100, 500)

    # Random scroll
    await page.evaluate("""
        () => {
            const scrollAmount = Math.random() * 500 + 200;
            window.scrollBy({ top: scrollAmount, behavior: 'smooth' });
        }
    """)
    await random_delay(500, 1500)

    # Scroll back up slightly
    await page.evaluate("""
        () => {
            window.scrollBy({ top: -100, behavior: 'smooth' });
        }
    """)
    await random_delay(300, 800)