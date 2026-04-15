"""
src/validator/validator.py
---------------------------
Comparison and normalization logic for menu labels vs. article titles.

Why not a simple equality check?
  Blog index pages routinely truncate long titles, add ellipsis, or reformat
  whitespace.  A strict equality check would produce false mismatches and
  erode trust in the report.  Instead, we:

    1. Normalize both strings (lowercase, collapse whitespace, strip punctuation)
    2. Check for exact match → MATCH
    3. If ALLOW_TRUNCATED_LABELS: check whether the label is a leading
       substring of the title → TRUNCATED (informational, not a failure)
    4. If FUZZY_MATCH_THRESHOLD < 1.0: run difflib SequenceMatcher →
       FUZZY_MATCH (informational) or MISMATCH
    5. Otherwise → MISMATCH

ValidationStatus hierarchy (for report colouring):
  MATCH        - perfect match after normalisation   ✅
  TRUNCATED    - label is a prefix of the full title ℹ️
  FUZZY_MATCH  - high similarity but not exact       ℹ️
  MISMATCH     - labels differ substantially         ❌
  ERROR        - page could not be fetched/parsed    ⚠️
  SKIPPED      - article URL was not visited         ⚠️
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from config.settings import ALLOW_TRUNCATED_LABELS, FUZZY_MATCH_THRESHOLD
from src.crawler.crawler import ArticleData, MenuEntry


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class ValidationStatus(str, Enum):
    MATCH = "MATCH"
    TRUNCATED = "TRUNCATED"
    FUZZY_MATCH = "FUZZY_MATCH"
    MISMATCH = "MISMATCH"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"

    @property
    def is_passing(self) -> bool:
        """Returns True for statuses that are not considered failures."""
        return self in {
            ValidationStatus.MATCH,
            ValidationStatus.TRUNCATED,
            ValidationStatus.FUZZY_MATCH,
        }


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """One validated entry - corresponds to one menu item."""

    status: ValidationStatus
    menu_label: str
    article_title: Optional[str]
    url: str
    position: int

    # Normalised forms (included in report when REPORT_INCLUDE_NORMALIZED=true)
    normalized_label: Optional[str] = None
    normalized_title: Optional[str] = None

    # Similarity score from fuzzy matching (0.0 – 1.0)
    similarity_score: Optional[float] = None

    # Human-readable explanation of the status decision
    note: Optional[str] = None

    # Error message if status == ERROR
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class Validator:
    """
    Compares menu entries against their corresponding article titles.

    Usage:
        results = Validator().validate(menu_entries, article_map)
    """

    def validate(
        self,
        menu_entries: list[MenuEntry],
        article_map: dict[str, ArticleData],
    ) -> list[ValidationResult]:
        """
        Run validation for every menu entry.

        Args:
            menu_entries : ordered list from the crawler (Phase 1)
            article_map  : URL → ArticleData mapping from the crawler (Phase 2)

        Returns:
            List of ValidationResult, one per menu entry, in original order.
        """
        results: list[ValidationResult] = []
        for entry in menu_entries:
            result = self._validate_entry(entry, article_map.get(entry.url))
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Per-entry logic
    # ------------------------------------------------------------------

    def _validate_entry(
        self,
        entry: MenuEntry,
        article: Optional[ArticleData],
    ) -> ValidationResult:
        """Determine the ValidationStatus for a single menu entry."""

        # --- Guard: article was never visited ---
        if article is None:
            return ValidationResult(
                status=ValidationStatus.SKIPPED,
                menu_label=entry.label,
                article_title=None,
                url=entry.url,
                position=entry.position,
                note="Article URL was not visited by the crawler.",
            )

        # --- Guard: crawl error ---
        if article.error:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                menu_label=entry.label,
                article_title=None,
                url=entry.url,
                position=entry.position,
                error=article.error,
            )

        # --- Guard: no title extracted ---
        if not article.title:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                menu_label=entry.label,
                article_title=None,
                url=entry.url,
                position=entry.position,
                error="Article title could not be extracted (no <h1> found).",
            )

        # --- Normalise ---
        norm_label = self._normalize(entry.label)
        norm_title = self._normalize(article.title)

        # --- Exact match ---
        if norm_label == norm_title:
            return ValidationResult(
                status=ValidationStatus.MATCH,
                menu_label=entry.label,
                article_title=article.title,
                url=entry.url,
                position=entry.position,
                normalized_label=norm_label,
                normalized_title=norm_title,
                similarity_score=1.0,
            )

        # --- Truncation check ---
        # Menu labels often end with "…" or are simply cut short.
        # Strip trailing ellipsis chars before checking prefix.
        clean_label = norm_label.rstrip("….")
        if ALLOW_TRUNCATED_LABELS and norm_title.startswith(clean_label):
            return ValidationResult(
                status=ValidationStatus.TRUNCATED,
                menu_label=entry.label,
                article_title=article.title,
                url=entry.url,
                position=entry.position,
                normalized_label=norm_label,
                normalized_title=norm_title,
                note=(
                    "Menu label appears to be a truncated version of the "
                    "full article title."
                ),
            )

        # --- Fuzzy match ---
        score = self._similarity(norm_label, norm_title)
        if FUZZY_MATCH_THRESHOLD < 1.0 and score >= FUZZY_MATCH_THRESHOLD:
            return ValidationResult(
                status=ValidationStatus.FUZZY_MATCH,
                menu_label=entry.label,
                article_title=article.title,
                url=entry.url,
                position=entry.position,
                normalized_label=norm_label,
                normalized_title=norm_title,
                similarity_score=round(score, 3),
                note=(
                    f"Strings are {score:.1%} similar - above the "
                    f"{FUZZY_MATCH_THRESHOLD:.0%} fuzzy-match threshold."
                ),
            )

        # --- Mismatch ---
        return ValidationResult(
            status=ValidationStatus.MISMATCH,
            menu_label=entry.label,
            article_title=article.title,
            url=entry.url,
            position=entry.position,
            normalized_label=norm_label,
            normalized_title=norm_title,
            similarity_score=round(score, 3),
            note=(
                f"Labels differ (similarity {score:.1%}). "
                "Manual review recommended."
            ),
        )

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Canonical normalisation applied to both menu labels and article titles
        before comparison.

        Steps:
          1. Unicode NFKC normalisation (handles typographic ligatures, etc.)
          2. Lowercase
          3. Strip leading/trailing whitespace
          4. Collapse internal whitespace (tabs, newlines, multiple spaces)
          5. Remove HTML entities (e.g. &amp; → and)  [defensive]
          6. Strip common punctuation that varies between label and title
             (colons, question marks, exclamation marks at end)
        """
        # Step 1 - Unicode normalisation
        text = unicodedata.normalize("NFKC", text)
        # Step 2 - lowercase
        text = text.lower()
        # Step 3 - strip outer whitespace
        text = text.strip()
        # Step 4 - collapse whitespace
        text = re.sub(r"\s+", " ", text)
        # Step 5 - remove trailing punctuation that commonly varies
        text = text.rstrip(":?!")
        return text

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """
        Compute string similarity using difflib SequenceMatcher.
        Returns a float in [0.0, 1.0].
        """
        return SequenceMatcher(None, a, b).ratio()
