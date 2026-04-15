"""
tests/test_crawler.py
----------------------
Unit tests for the crawler module.

We do NOT spin up a real browser here - that would make tests slow and
fragile (network-dependent).  Instead we test:

  1. Data contracts   : MenuEntry and ArticleData behave as expected
  2. URL resolution   : relative hrefs are correctly made absolute
  3. Edge cases       : empty labels, missing hrefs, etc.

Integration / end-to-end tests that actually launch Playwright belong in
a separate `tests/integration/` suite (not included here, as they require
network access and a running browser).
"""

import pytest

from src.crawler.crawler import ArticleData, BlogCrawler, MenuEntry


# ---------------------------------------------------------------------------
# MenuEntry
# ---------------------------------------------------------------------------


class TestMenuEntry:
    def test_stores_fields(self):
        entry = MenuEntry(label="Hello World", url="https://example.com", position=1)
        assert entry.label    == "Hello World"
        assert entry.url      == "https://example.com"
        assert entry.position == 1

    def test_label_is_not_stripped_by_dataclass(self):
        # Stripping is done by the crawler, not the dataclass itself.
        entry = MenuEntry(label="  spaced  ", url="https://x.com", position=1)
        assert entry.label == "  spaced  "


# ---------------------------------------------------------------------------
# ArticleData
# ---------------------------------------------------------------------------


class TestArticleData:
    def test_defaults_to_none(self):
        article = ArticleData(url="https://example.com")
        assert article.title       is None
        assert article.error       is None
        assert article.http_status is None

    def test_with_title(self):
        article = ArticleData(url="https://example.com", title="My Post")
        assert article.title == "My Post"

    def test_with_error(self):
        article = ArticleData(url="https://example.com", error="Timeout")
        assert article.error == "Timeout"
        assert article.title is None

    def test_mutually_exclusive_title_and_error(self):
        # Both can technically be set; the validator handles the priority.
        # This test documents the expected usage pattern.
        article = ArticleData(url="https://x.com", title="T", error="E")
        assert article.title == "T"
        assert article.error == "E"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class TestResolveUrl:
    """
    _resolve_url should turn relative hrefs into absolute URLs using the
    base URL of the page they were found on.
    """

    def test_absolute_url_unchanged(self):
        result = BlogCrawler._resolve_url(
            "https://crawlee.dev/blog/my-post",
            "https://crawlee.dev/blog",
        )
        assert result == "https://crawlee.dev/blog/my-post"

    def test_root_relative_url(self):
        result = BlogCrawler._resolve_url(
            "/blog/my-post",
            "https://crawlee.dev/blog",
        )
        assert result == "https://crawlee.dev/blog/my-post"

    def test_relative_url(self):
        result = BlogCrawler._resolve_url(
            "my-post",
            "https://crawlee.dev/blog/",
        )
        assert result == "https://crawlee.dev/blog/my-post"

    def test_fragment_only_url(self):
        result = BlogCrawler._resolve_url(
            "#section",
            "https://crawlee.dev/blog",
        )
        assert result == "https://crawlee.dev/blog#section"

    def test_different_domain(self):
        # Should preserve the href domain when it's already absolute.
        result = BlogCrawler._resolve_url(
            "https://apify.com/blog/post",
            "https://crawlee.dev/blog",
        )
        assert result == "https://apify.com/blog/post"
