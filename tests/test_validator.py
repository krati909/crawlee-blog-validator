"""
tests/test_validator.py
------------------------
Unit tests for the Validator and its normalisation logic.

These tests do NOT require a browser or network access - they work
entirely with in-memory fixtures.  This means they run in milliseconds
and are suitable for a pre-commit hook or a fast CI gate.

Coverage areas:
  - _normalize()   : unicode, whitespace, case, trailing punctuation
  - validate()     : MATCH, TRUNCATED, FUZZY_MATCH, MISMATCH, ERROR, SKIPPED
"""

import pytest

from src.crawler.crawler import ArticleData, MenuEntry
from src.validator.validator import ValidationStatus, Validator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_entry(label: str, url: str = "https://crawlee.dev/blog/post", pos: int = 1) -> MenuEntry:
    return MenuEntry(label=label, url=url, position=pos)


def make_article(title: str | None = None, error: str | None = None) -> ArticleData:
    return ArticleData(url="https://crawlee.dev/blog/post", title=title, error=error)


validator = Validator()


# ---------------------------------------------------------------------------
# _normalize tests
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercases(self):
        assert validator._normalize("Hello World") == "hello world"

    def test_strips_whitespace(self):
        assert validator._normalize("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self):
        assert validator._normalize("hello   world\ttab") == "hello world tab"

    def test_removes_trailing_colon(self):
        assert validator._normalize("hello world:") == "hello world"

    def test_removes_trailing_question_mark(self):
        assert validator._normalize("hello world?") == "hello world"

    def test_unicode_normalisation(self):
        # NFKC: fi ligature → fi
        assert validator._normalize("\ufb01le") == "file"

    def test_preserves_internal_punctuation(self):
        # Hyphens and commas inside the string should be kept
        assert validator._normalize("crawlee: a node.js library") == "crawlee: a node.js library"

    def test_empty_string(self):
        assert validator._normalize("") == ""


# ---------------------------------------------------------------------------
# validate() - status outcomes
# ---------------------------------------------------------------------------


class TestValidateStatus:

    def test_exact_match(self):
        entry = make_entry("Announcing Crawlee for Python")
        article = make_article("Announcing Crawlee for Python")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.MATCH

    def test_case_insensitive_match(self):
        entry = make_entry("Announcing Crawlee for Python")
        article = make_article("announcing crawlee for python")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.MATCH

    def test_whitespace_normalisation_leads_to_match(self):
        entry = make_entry("Web  Scraping  Tips")
        article = make_article("Web Scraping Tips")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.MATCH

    def test_truncated_label(self):
        entry = make_entry("Web Scraping in 2024")
        article = make_article("Web Scraping in 2024: The Complete Guide")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.TRUNCATED

    def test_truncated_label_with_ellipsis(self):
        entry = make_entry("Web Scraping in 2024…")
        article = make_article("Web Scraping in 2024: The Complete Guide")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.TRUNCATED

    def test_mismatch(self):
        entry = make_entry("Introduction to Crawlee")
        article = make_article("Getting Started with Apify")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.MISMATCH

    def test_error_from_crawl(self):
        entry = make_entry("Some Post")
        article = make_article(error="ConnectionError: timeout")
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.ERROR
        assert "ConnectionError" in results[0].error

    def test_no_h1_found(self):
        entry = make_entry("Some Post")
        article = make_article(title=None, error=None)
        results = validator.validate([entry], {entry.url: article})
        assert results[0].status == ValidationStatus.ERROR

    def test_skipped_when_article_missing(self):
        entry = make_entry("Missing Post")
        results = validator.validate([entry], {})   # empty article_map
        assert results[0].status == ValidationStatus.SKIPPED

    def test_preserves_order(self):
        entries = [
            make_entry("Post A", url="https://example.com/a", pos=1),
            make_entry("Post B", url="https://example.com/b", pos=2),
            make_entry("Post C", url="https://example.com/c", pos=3),
        ]
        article_map = {
            "https://example.com/a": ArticleData(url="https://example.com/a", title="Post A"),
            "https://example.com/b": ArticleData(url="https://example.com/b", title="Post B"),
            "https://example.com/c": ArticleData(url="https://example.com/c", title="Post C"),
        }
        results = validator.validate(entries, article_map)
        assert [r.position for r in results] == [1, 2, 3]

    def test_multiple_results_mixed_statuses(self):
        entries = [
            make_entry("Exact Title",      url="https://x.com/a", pos=1),
            make_entry("Short Title",      url="https://x.com/b", pos=2),
            make_entry("Completely Wrong", url="https://x.com/c", pos=3),
        ]
        article_map = {
            "https://x.com/a": ArticleData(url="https://x.com/a", title="Exact Title"),
            "https://x.com/b": ArticleData(url="https://x.com/b", title="Short Title: Full Version"),
            "https://x.com/c": ArticleData(url="https://x.com/c", title="Something Else Entirely"),
        }
        results = validator.validate(entries, article_map)
        statuses = [r.status for r in results]
        assert ValidationStatus.MATCH     in statuses
        assert ValidationStatus.TRUNCATED in statuses
        assert ValidationStatus.MISMATCH  in statuses


# ---------------------------------------------------------------------------
# is_passing property
# ---------------------------------------------------------------------------


class TestIsPassingProperty:
    @pytest.mark.parametrize("status,expected", [
        (ValidationStatus.MATCH,       True),
        (ValidationStatus.TRUNCATED,   True),
        (ValidationStatus.FUZZY_MATCH, True),
        (ValidationStatus.MISMATCH,    False),
        (ValidationStatus.ERROR,       False),
        (ValidationStatus.SKIPPED,     False),
    ])
    def test_is_passing(self, status, expected):
        assert status.is_passing == expected
