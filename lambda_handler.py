"""
lambda_handler.py
------------------
AWS Lambda entry point.

The handler follows the standard Lambda contract:
  - Receives an `event` dict and a `context` object
  - Returns a dict that Lambda serialises as the function response

Invocation examples
-------------------
  # Full run (default)
  aws lambda invoke --function-name crawlee-blog-validator \
      --payload '{}' output.json

  # Limit to first 5 articles (useful for smoke-testing in CI)
  aws lambda invoke --function-name crawlee-blog-validator \
      --payload '{"max_articles": 5}' output.json

Response shape
--------------
  Success:
  {
    "statusCode": 200,
    "body": {
      "run_id": "...",
      "summary": { "total": 25, "matched": 24, ... },
      "report_json": "/tmp/reports/report_<run_id>.json",
      "report_html": "/tmp/reports/report_<run_id>.html"
    }
  }

  Failure:
  {
    "statusCode": 500,
    "body": { "error": "...", "detail": "..." }
  }

Lambda configuration notes
---------------------------
  - Memory  : 1024 MB recommended (Chromium is memory-hungry)
  - Timeout : 300 seconds (5 minutes)
  - /tmp    : used for report output (512 MB ephemeral storage)
  - Concurrency: set reserved concurrency = 1 if you want to prevent
    parallel runs competing for /tmp space
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    """
    Main Lambda entry point.

    Args:
        event   : dict - supports optional keys:
                    max_articles (int) - override MAX_ARTICLES setting
        context : LambdaContext (unused, but required by the interface)

    Returns:
        API-Gateway-compatible response dict with statusCode + body.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logger.info("Lambda invoked - run_id=%s  event=%s", run_id, json.dumps(event))

    # ------------------------------------------------------------------
    # Apply event-level overrides to environment settings
    # ------------------------------------------------------------------
    if "max_articles" in event:
        os.environ["MAX_ARTICLES"] = str(event["max_articles"])
        logger.info("MAX_ARTICLES overridden to %s via event.", event["max_articles"])

    # Use a unique storage dir per run to prevent warm container reuse
    # from replaying stale Crawlee request queues across invocations.
    os.environ["CRAWLEE_STORAGE_DIR"] = f"/tmp/storage/{run_id}"

    # ------------------------------------------------------------------
    # Run the pipeline
    # ------------------------------------------------------------------
    try:
        # Import here (not at module level) so that env overrides above
        # take effect before settings.py is evaluated.
        from orchestrator import run_pipeline

        result = run_pipeline()
        result["run_id"] = run_id

        return {
            "statusCode": 200,
            "body": result,
        }

    except Exception as exc:
        logger.error("Pipeline failed: %s\n%s", exc, traceback.format_exc())
        return {
            "statusCode": 500,
            "body": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "run_id": run_id,
            },
        }
