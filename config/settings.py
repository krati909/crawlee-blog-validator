"""
config/settings.py
------------------
Centralized configuration for the Crawlee Blog Validator.

All tuneable parameters live here so that:
  - Nothing is hard-coded in business logic
  - Lambda environment variables can override defaults at runtime
  - Tests can override values via environment variables without code changes
"""

import os
import platform


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------

BLOG_INDEX_URL: str = os.getenv(
    "BLOG_INDEX_URL",
    "https://crawlee.dev/blog",
)

# ---------------------------------------------------------------------------
# Crawler behaviour
# ---------------------------------------------------------------------------

# Maximum number of article pages to visit in a single run.
# Set to 0 (or leave unset) for no limit.
MAX_ARTICLES: int = int(os.getenv("MAX_ARTICLES", "0"))

# Milliseconds to wait after a page loads before extracting content.
# A small delay gives JS-rendered content time to settle.
PAGE_SETTLE_MS: int = int(os.getenv("PAGE_SETTLE_MS", "1500"))

# Number of times Crawlee will retry a failed request before marking it as an error.
MAX_REQUEST_RETRIES: int = int(os.getenv("MAX_REQUEST_RETRIES", "3"))

# Maximum number of concurrent browser pages.
# Keep low in Lambda to stay within memory limits.
MAX_CONCURRENCY: int = int(os.getenv("MAX_CONCURRENCY", "1"))

# ---------------------------------------------------------------------------
# Playwright / Browser
# ---------------------------------------------------------------------------

# Run Chromium in headless mode (must be True in Lambda).
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"

# Extra Chromium launch args required for Lambda / containerised environments.
CHROMIUM_ARGS: list[str] = (
    [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--single-process",
    ]
    if platform.system() == "Linux"
    else []  # Windows/Mac: let Chromium use its defaults
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# If True, a menu label that is a leading substring of the article title
# is reported as TRUNCATED (informational) rather than MISMATCH (failure).
ALLOW_TRUNCATED_LABELS: bool = (
    os.getenv("ALLOW_TRUNCATED_LABELS", "true").lower() == "true"
)

# Minimum ratio (0–1) for fuzzy-match fallback using difflib SequenceMatcher.
# Set to 1.0 to disable fuzzy matching entirely.
FUZZY_MATCH_THRESHOLD: float = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.85"))

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

# Directory where report files are written.
# Lambda functions can write to /tmp (512 MB ephemeral storage).
REPORT_OUTPUT_DIR: str = os.getenv("REPORT_OUTPUT_DIR", "./reports")

# Whether to include the full normalised strings in the JSON report.
# Useful for debugging; can be disabled for cleaner stakeholder reports.
REPORT_INCLUDE_NORMALIZED: bool = (
    os.getenv("REPORT_INCLUDE_NORMALIZED", "true").lower() == "true"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
