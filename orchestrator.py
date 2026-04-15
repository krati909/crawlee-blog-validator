"""
orchestrator.py
---------------
Ties together the three pipeline stages:

  Crawler → Validator → Reporter

This module is the single entry point for both:
  - Local execution   : python orchestrator.py
  - Lambda invocation : imported by lambda_handler.py

Keeping orchestration separate from the Lambda handler means the pipeline
can be run and tested locally without any AWS infrastructure.
"""

from __future__ import annotations

import logging
import sys

from config.settings import LOG_LEVEL
from src.crawler.crawler import run_crawler
from src.reporter.reporter import ReportSummary, Reporter
from src.validator.validator import ValidationResult, Validator

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline() -> dict:
    """
    Execute the full validation pipeline.

    Returns a dict suitable for returning directly from the Lambda handler,
    containing the summary statistics and the file paths of both reports.

    Raises:
        RuntimeError: if the crawler finds no menu entries (likely a site
                      structure change - requires human investigation).
    """
    logger.info("=" * 60)
    logger.info("Crawlee Blog Validator - pipeline starting")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Stage 1: Crawl
    # ------------------------------------------------------------------
    logger.info("[Stage 1/3] Crawling …")
    menu_entries, article_map = run_crawler()

    if not menu_entries:
        raise RuntimeError(
            "Crawler returned no menu entries. "
            "The blog page structure may have changed, or the page failed to load."
        )

    logger.info(
        "[Stage 1/3] Complete - %d menu entries, %d articles crawled.",
        len(menu_entries),
        len(article_map),
    )

    # ------------------------------------------------------------------
    # Stage 2: Validate
    # ------------------------------------------------------------------
    logger.info("[Stage 2/3] Validating …")
    results: list[ValidationResult] = Validator().validate(menu_entries, article_map)
    logger.info("[Stage 2/3] Complete - %d results.", len(results))

    # ------------------------------------------------------------------
    # Stage 3: Report
    # ------------------------------------------------------------------
    logger.info("[Stage 3/3] Generating reports …")
    summary, json_path, html_path = Reporter().generate(results)
    logger.info("[Stage 3/3] Complete.")

    # ------------------------------------------------------------------
    # Log summary to stdout (visible in CloudWatch)
    # ------------------------------------------------------------------
    _log_summary(summary)

    return {
        "summary": summary.to_dict(),
        "report_json": json_path,
        "report_html": html_path,
    }


def _log_summary(summary: ReportSummary) -> None:
    logger.info("=" * 60)
    logger.info("RESULTS SUMMARY")
    logger.info("  Total     : %d", summary.total)
    logger.info("  ✅ Match   : %d", summary.matched)
    logger.info("  ℹ️  Truncated: %d", summary.truncated)
    logger.info("  ℹ️  Fuzzy   : %d", summary.fuzzy)
    logger.info("  ❌ Mismatch: %d", summary.mismatched)
    logger.info("  ⚠️  Errors  : %d", summary.errors)
    logger.info("  Pass Rate : %s", summary.pass_rate)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Local entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = run_pipeline()
    print("\nReports written:")
    print(f"  JSON : {result['report_json']}")
    print(f"  HTML : {result['report_html']}")
