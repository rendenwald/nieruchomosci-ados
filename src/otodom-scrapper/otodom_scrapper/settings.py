"""Scrapy settings for otodom-scrapper project."""

BOT_NAME = "otodom_scrapper"

SPIDER_MODULES = ["otodom_scrapper.spiders"]
NEWSPIDER_MODULE = "otodom_scrapper.spiders"

# Crawl responsibly — obey robots.txt
ROBOTSTXT_OBEY = True

# Playwright configuration for JS rendering
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# Throttle settings — polite crawling
DOWNLOAD_DELAY = 2.0
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# Pipeline
ITEM_PIPELINES = {
    "otodom_scrapper.pipelines.OtodomPipeline": 300,
}

# Logging
LOG_LEVEL = "INFO"
