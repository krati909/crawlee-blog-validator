"""
src/crawler/crawler.py
-----------------------
Responsible for all browser-based data extraction.

Two-phase crawl strategy:
  Phase 1 - Index page  : Visit the blog index and extract every menu/sidebar
                          entry (visible label + href URL).
  Phase 2 - Article pages: Visit each article URL and extract the <h1> title.

Why Crawlee over raw Playwright?
  Crawlee adds automatic retries, request deduplication, configurable
  concurrency, and structured error handling on top of Playwright.  These are
  production QA concerns - not luxuries.

Data contracts:
  MenuEntry   - one item from the blog sidebar/index
  ArticleData - the scraped title (or error) for one article page
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee import ConcurrencySettings
from datetime import timedelta

from urllib.parse import urljoin, urlparse

from config.settings import (
    BLOG_INDEX_URL,
    CHROMIUM_ARGS,
    HEADLESS,
    MAX_ARTICLES,
    MAX_CONCURRENCY,
    MAX_REQUEST_RETRIES,
    PAGE_SETTLE_MS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class MenuEntry:
    """A single entry extracted from the blog index/sidebar."""

    label: str        # Visible link text shown in the menu
    url: str          # Absolute URL the entry links to
    position: int     # 1-based position in the menu (for ordering in reports)


@dataclass
class ArticleData:
    """Result of visiting one article page."""

    url: str
    title: Optional[str] = None          # <h1> text if successfully extracted
    error: Optional[str] = None          # Human-readable error message, if any
    http_status: Optional[int] = None    # HTTP status code returned by the page


# ---------------------------------------------------------------------------
# BlogCrawler
# ---------------------------------------------------------------------------


class BlogCrawler:
    """
    Orchestrates the two-phase Crawlee crawl.

    Usage:
        crawler = BlogCrawler()
        menu_entries, article_map = await crawler.run()
    """

    def __init__(self) -> None:
        self._menu_entries: list[MenuEntry] = []
        # Maps article URL → ArticleData
        self._article_map: dict[str, ArticleData] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
    ) -> tuple[list[MenuEntry], dict[str, ArticleData]]:
        """
        Execute the full two-phase crawl.

        Returns:
            menu_entries : ordered list of MenuEntry items found on the index page
            article_map  : dict mapping each article URL to its ArticleData
        """
        logger.info("Phase 1: Crawling blog index - %s", BLOG_INDEX_URL)
        await self._crawl_index()

        if not self._menu_entries:
            logger.warning("No menu entries found on the index page. Aborting.")
            return [], {}

        logger.info(
            "Phase 1 complete: %d menu entries found.", len(self._menu_entries)
        )

        urls_to_visit = [entry.url for entry in self._menu_entries]
        if MAX_ARTICLES and MAX_ARTICLES > 0:
            urls_to_visit = urls_to_visit[:MAX_ARTICLES]
            # Trim menu_entries to match - no point validating entries we won't visit
            self._menu_entries = self._menu_entries[:MAX_ARTICLES]
            logger.info("MAX_ARTICLES=%d - limiting crawl to first %d articles.",
                        MAX_ARTICLES, MAX_ARTICLES)

        logger.info("Phase 2: Crawling %d article pages.", len(urls_to_visit))
        await self._crawl_articles(urls_to_visit)
        logger.info("Phase 2 complete.")

        return self._menu_entries, self._article_map

    # ------------------------------------------------------------------
    # Phase 1 - index page
    # ------------------------------------------------------------------

    async def _crawl_index(self) -> None:
        """
        Visit the blog index page and populate self._menu_entries.

        Selector strategy:
          The crawlee.dev blog uses a sidebar list of article links.
          We target <a> elements inside the blog post listing.
          Multiple CSS selectors are tried in priority order so that the
          crawler degrades gracefully if the site's markup changes.
        """

        # We only need to visit ONE page in this phase.
        crawler = self._build_crawler(max_requests_per_crawl=1)

        @crawler.router.default_handler
        async def index_handler(context: PlaywrightCrawlingContext) -> None:
            page = context.page
            logger.debug("Index page loaded: %s", page.url)

            # Wait for the page to settle (JS rendering)
            await page.wait_for_timeout(PAGE_SETTLE_MS)

            # Wait until at least one blog link is present in the DOM
            # before extracting - guards against blank page on slow Lambda cold starts
            try:
                await page.wait_for_selector("a[href*='/blog/']", timeout=30000)
            except Exception:
                logger.error("Timed out waiting for blog links to appear in DOM.")
                self._menu_entries = []
                return

            # Use JavaScript to extract all blog post links directly from the DOM.
            # We first try to scope to the sidebar (which has the complete list),
            # then fall back to the full page if the sidebar isn't found.
            raw_links: list[dict] = await page.evaluate("""
                () => {
                    // Try sidebar first (complete list of all posts)
                    const sidebar = document.querySelector('aside') ||
                                    document.querySelector('[class*="sidebar"]') ||
                                    document.querySelector('[class*="Sidebar"]');
                    const container = sidebar || document;

                    const links = Array.from(container.querySelectorAll('a[href]'));
                    return links
                        .map(a => ({ label: a.innerText.trim(), href: a.getAttribute('href') }))
                        .filter(item =>
                            item.label &&
                            item.href &&
                            item.href.includes('/blog/') &&
                            !item.href.startsWith('#') &&
                            !item.href.includes('/blog/page/') &&
                            item.href !== '/blog' &&
                            item.href !== '/blog/'
                        );
                }
            """)

            # Deduplicate by URL while preserving order
            seen_urls: set[str] = set()
            entries: list[MenuEntry] = []
            position = 1
            for item in raw_links:
                absolute_url = self._resolve_url(item["href"], BLOG_INDEX_URL)
                # Skip index page itself (handles /blog#section after resolution)
                parsed = urlparse(absolute_url)
                index_parsed = urlparse(BLOG_INDEX_URL)
                if parsed.path == index_parsed.path:
                    continue
                if absolute_url not in seen_urls:
                    seen_urls.add(absolute_url)
                    entries.append(MenuEntry(label=item["label"], url=absolute_url,
                                             position=position))
                    position += 1

            if entries:
                logger.info("JS extraction found %d blog entries.", len(entries))
            else:
                logger.error(
                    "No blog entries found via JS extraction. "
                    "The page structure may have changed."
                )

            self._menu_entries = entries

        await crawler.run([BLOG_INDEX_URL])

    # ------------------------------------------------------------------
    # Phase 2 - article pages
    # ------------------------------------------------------------------

    async def _crawl_articles(self, urls: list[str]) -> None:
        """
        Visit each article URL and extract the <h1> title.

        Results are stored in self._article_map.
        """
        # Pre-populate map so we can detect any URL that Crawlee skips
        for url in urls:
            self._article_map[url] = ArticleData(url=url)

        crawler = self._build_crawler(max_requests_per_crawl=len(urls))

        @crawler.router.default_handler
        async def article_handler(context: PlaywrightCrawlingContext) -> None:
            page = context.page
            # Use the original request URL as the key, not page.url after navigation.
            # page.url can differ due to redirects or trailing slash normalisation,
            # which would cause the article_map lookup to miss.
            url = context.request.url
            logger.debug("Visiting article: %s", url)

            await page.wait_for_timeout(PAGE_SETTLE_MS)

            # --- Extract <h1> title ---
            h1 = await page.query_selector("h1")
            if h1:
                title = (await h1.inner_text()).strip()
                logger.debug("Title found: %r", title)
                self._article_map[url] = ArticleData(url=url, title=title)
            else:
                logger.warning("No <h1> found on page: %s", url)
                self._article_map[url] = ArticleData(
                    url=url,
                    error="No <h1> element found on page",
                )

        # Attach a failed-request handler to capture errors gracefully
        @crawler.failed_request_handler
        async def error_handler(context: PlaywrightCrawlingContext, error: Exception) -> None:
            url = context.request.url
            logger.error("Error crawling %s: %s", url, error)
            self._article_map[url] = ArticleData(
                url=url,
                error=f"{type(error).__name__}: {error}",
            )

        await crawler.run(urls)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_crawler(self, max_requests_per_crawl: int) -> PlaywrightCrawler:
        """
        Factory method - builds a PlaywrightCrawler with shared settings.

        Centralising construction means we never forget to set headless mode,
        Lambda-safe Chromium args, or retry counts.
        """
        return PlaywrightCrawler(
            max_requests_per_crawl=max_requests_per_crawl,
            max_request_retries=MAX_REQUEST_RETRIES,
            concurrency_settings=ConcurrencySettings(
                min_concurrency=1,
                max_concurrency=MAX_CONCURRENCY,
                desired_concurrency=MAX_CONCURRENCY,
            ),
            headless=HEADLESS,
            browser_launch_options={"args": CHROMIUM_ARGS},
            request_handler_timeout=timedelta(seconds=120),
        )

    @staticmethod
    def _resolve_url(href: str, base: str) -> str:
        """Convert a relative href to an absolute URL."""
        return urljoin(base, href)


# ---------------------------------------------------------------------------
# Convenience wrapper for synchronous callers (e.g., Lambda handler)
# ---------------------------------------------------------------------------


def run_crawler() -> tuple[list[MenuEntry], dict[str, ArticleData]]:
    """Synchronous entry point - runs the async crawler in a new event loop."""
    return asyncio.run(BlogCrawler().run())
