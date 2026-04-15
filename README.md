# Crawlee Blog Validator

An automated QA pipeline that crawls [crawlee.dev/blog](https://crawlee.dev/blog),
validates that each blog listing label matches its article's `<h1>` title, and
generates a structured JSON + HTML report. Deployed as an AWS Lambda Docker function.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Local Development](#local-development)
- [Running Tests](#running-tests)
- [Docker & AWS Lambda Deployment](#docker--aws-lambda-deployment)
- [One-Click Scripts](#one-click-scripts)
- [Invoking the Lambda](#invoking-the-lambda)
- [Configuration Reference](#configuration-reference)
- [Report Format](#report-format)
- [Architecture](#architecture)
- [Design Decisions](#design-decisions)

---

## Project Structure

```
crawlee-blog-validator/
├── src/
│   ├── crawler/crawler.py        # Two-phase Crawlee scraper
│   ├── validator/validator.py    # Normalised comparison logic
│   └── reporter/reporter.py      # JSON + HTML report generation
├── tests/                        # Unit tests (no browser/network required)
├── config/settings.py            # All tuneable settings (env-var driven)
├── orchestrator.py               # Pipeline: crawl → validate → report
├── lambda_handler.py             # AWS Lambda entry point
├── Dockerfile                    # Lambda-compatible Docker image
├── requirements.txt
├── .env.example                  # Copy to .env for local use
├── aws/
│   ├── deploy.ps1                # One-click: build image + push to ECR + update Lambda
│   ├── invoke.ps1                # One-click: invoke Lambda + print result
│   ├── setup-aws.ps1             # One-click: create ECR repo + IAM role + Lambda function (run once)
│   └── payload.json              # Default invoke payload
└── setup/
    ├── windows.ps1               # One-click local setup (Windows)
    └── linux_mac.sh              # One-click local setup (Mac/Linux)
```

---

## Local Development

### Prerequisites

- Python 3.12
- Docker Desktop
- AWS CLI v2 - [install guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
- AWS credentials configured: `aws configure`

### 1. One-click local setup

**Windows:**
```powershell
.\setup\windows.ps1
```

**Mac/Linux:**
```bash
bash setup/linux_mac.sh
```

This creates a `.venv`, installs dependencies, installs Playwright Chromium, and copies `.env.example` → `.env`.

### 2. Configure environment

Edit `.env` - the defaults work out of the box, but you can tweak:

```dotenv
MAX_ARTICLES=0          # 0 = no limit; set e.g. 5 for a quick smoke test
PAGE_SETTLE_MS=1500     # ms to wait after page load before extracting
HEADLESS=true           # set false to watch the browser locally
FUZZY_MATCH_THRESHOLD=0.85
```

### 3. Run locally

```powershell
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Mac/Linux

python orchestrator.py
```

Reports are written to `./reports/` as `report_<timestamp>.json` and `report_<timestamp>.html`.

---

## Running Tests

```powershell
pytest tests/ -v
```

Tests are fully offline - no browser or network required. They run in milliseconds.

---

## Docker & AWS Lambda Deployment

### How it works

Lambda functions have a 250 MB unzipped size limit for zip deployments. Playwright +
Chromium alone exceed that. The solution is a **Docker image** deployed to ECR -
Lambda supports images up to 10 GB.

The image is built from the official AWS Lambda Python 3.12 base image, which includes
the Lambda Runtime Interface Client pre-configured.

### First-time AWS setup (run once)

You need three things in AWS before deploying: an ECR repository, an IAM execution
role, and the Lambda function itself.

**Set your AWS details as environment variables first:**

```powershell
$env:AWS_ACCOUNT_ID = "123456789012"
$env:AWS_REGION     = "us-east-1"
$env:IMAGE_URI      = "$($env:AWS_ACCOUNT_ID).dkr.ecr.$($env:AWS_REGION).amazonaws.com/crawlee-blog-validator"
```

Then run the one-time setup script:

```powershell
.\aws\setup-aws.ps1
```

This creates the ECR repo, IAM role, builds + pushes the image, and creates the Lambda function.

> **Note:** After first deploy, update Lambda to production settings:
> ```powershell
> aws lambda update-function-configuration `
>   --function-name crawlee-blog-validator `
>   --memory-size 2048 --timeout 600 `
>   --environment "Variables={CRAWLEE_STORAGE_DIR=/tmp/storage,REPORT_OUTPUT_DIR=/tmp/reports,MAX_CONCURRENCY=3}" `
>   --region $env:AWS_REGION
> ```

### Deploying updates (after code changes)

```powershell
.\aws\deploy.ps1
```

This rebuilds the image, pushes to ECR, and updates the Lambda function - one command.

---

## One-Click Scripts

| Script | Purpose | When to run |
|--------|---------|-------------|
| `.\setup\windows.ps1` | Local Python environment setup | Once, after cloning |
| `.\aws\setup-aws.ps1` | Create ECR + IAM role + Lambda function | Once, first deployment |
| `.\aws\deploy.ps1` | Build image → push ECR → update Lambda | Every time you change code |
| `.\aws\invoke.ps1` | Invoke Lambda and print results | To test the deployed function |

---

## Invoking the Lambda

**Via script (recommended):**
```powershell
.\aws\invoke.ps1                  # full run (async, polls CloudWatch)
.\aws\invoke.ps1 -MaxArticles 3   # smoke test (synchronous, fast)
```

**Check CloudWatch logs:**
```powershell
aws logs tail /aws/lambda/crawlee-blog-validator --follow --region $env:AWS_REGION
```

---

## Configuration Reference

All settings are environment variables. Set them in `.env` for local runs, or via
`aws lambda update-function-configuration` for Lambda.

| Variable | Default | Description |
|----------|---------|-------------|
| `BLOG_INDEX_URL` | `https://crawlee.dev/blog` | Target URL to crawl |
| `MAX_ARTICLES` | `0` | Max articles to visit (0 = unlimited) |
| `PAGE_SETTLE_MS` | `1500` | Wait time (ms) after page load |
| `MAX_REQUEST_RETRIES` | `3` | Crawlee retry count per request |
| `HEADLESS` | `true` | Run browser headless (must be true in Lambda) |
| `ALLOW_TRUNCATED_LABELS` | `true` | Treat prefix labels as passing (TRUNCATED) |
| `FUZZY_MATCH_THRESHOLD` | `0.85` | Similarity ratio for fuzzy match (0–1) |
| `REPORT_OUTPUT_DIR` | `./reports` | Where to write reports (`/tmp/reports` in Lambda) |
| `REPORT_INCLUDE_NORMALIZED` | `true` | Include normalised strings in JSON report |
| `CRAWLEE_STORAGE_DIR` | `./storage` | Crawlee internal storage (`/tmp/storage` in Lambda) |
| `LOG_LEVEL` | `INFO` | Python logging level |

---

## Report Format

Two files are generated per run: `report_<run_id>.json` and `report_<run_id>.html`.

### Validation statuses

| Status | Meaning | Passing? |
|--------|---------|----------|
| `MATCH` | Exact match after normalisation | ✅ |
| `TRUNCATED` | Menu label is a prefix of the full title | ✅ |
| `FUZZY_MATCH` | Similarity ≥ threshold | ✅ |
| `MISMATCH` | Labels differ substantially | ❌ |
| `ERROR` | Page failed to load or no `<h1>` found | ❌ |
| `SKIPPED` | Article URL was not visited | ❌ |

### JSON structure

```json
{
  "run_id": "20260414T120000Z",
  "generated_at": "2026-04-14T12:00:00+00:00",
  "target_url": "https://crawlee.dev/blog",
  "summary": {
    "total": 25,
    "matched": 22,
    "truncated": 2,
    "fuzzy_match": 0,
    "mismatched": 0,
    "errors": 1,
    "skipped": 0,
    "passing": 24,
    "failing": 1,
    "pass_rate": "96.0%"
  },
  "results": [
    {
      "position": 1,
      "status": "MATCH",
      "menu_label": "Announcing Crawlee for Python",
      "article_title": "Announcing Crawlee for Python",
      "url": "https://crawlee.dev/blog/crawlee-for-python",
      "similarity_score": 1.0,
      "normalized_label": "announcing crawlee for python",
      "normalized_title": "announcing crawlee for python"
    }
  ]
}
```

---

## Architecture

```
lambda_handler.py          ← AWS Lambda entry point
      │
      ▼
orchestrator.py            ← coordinates stages, logs summary to CloudWatch
      │
      ├── [Stage 1/3] crawler.py
      │       Phase 1: visit blog index, extract menu entries (label + URL)
      │       Phase 2: visit each article page, extract <h1> title
      │       returns: (menu_entries, article_map)
      │
      ├── [Stage 2/3] validator.py
      │       normalise → exact match → truncation check → fuzzy match → mismatch
      │       returns: [ValidationResult, ...]
      │
      └── [Stage 3/3] reporter.py
              writes JSON + HTML reports to REPORT_OUTPUT_DIR
              returns: (summary, json_path, html_path)
```

---

## Design Decisions

**Docker over zip + layers** - Playwright + Chromium exceed Lambda's 250 MB zip limit.
Docker images support up to 10 GB and give fully reproducible builds.

**Two-phase crawl** - Phase 1 collects all menu entries; Phase 2 batch-fetches articles.
This isolates failures: a broken index selector is immediately obvious, and a single
article failure doesn't affect the rest of the crawl.

**JS-based link extraction over CSS selectors** - The blog index is a Docusaurus
React app. CSS class names are unstable across renders and environments (locally vs
Lambda headless). Instead, Phase 1 uses `page.evaluate()` to run JavaScript directly
in the browser, scanning all `<a href>` elements and filtering by URL pattern. This
is immune to class name changes and works consistently across environments.

**Normalised comparison over strict equality** - Blog index pages truncate titles,
collapse whitespace, and drop trailing punctuation. Strict `==` would produce noisy
false mismatches. The normaliser handles unicode (NFKC), whitespace, case, and
trailing punctuation before comparing.

**TRUNCATED / FUZZY_MATCH as passing** - These represent known, acceptable variations
(truncated menu labels, minor reformatting). They are flagged visually in the report
so a human reviewer can inspect them, but they don't fail the run.

**`context.request.url` over `page.url` for article map keys** - After navigation,
`page.url` may differ from the requested URL due to redirects or trailing slash
normalisation. Using the original request URL as the map key ensures Phase 1 and
Phase 2 always use the same key, preventing false SKIPPED results.

**Unique Crawlee storage dir per invocation** - Lambda reuses warm containers across
invocations. Crawlee persists its request queue to disk, so a warm container would
see previously-visited URLs as already processed and skip them. Setting
`CRAWLEE_STORAGE_DIR=/tmp/storage/<run_id>` gives each invocation a clean slate.

**Lambda configuration** - 2048 MB memory (Chromium needs ~300 MB per tab),
600s timeout (25 articles at concurrency 3 takes ~4 minutes), `MAX_CONCURRENCY=3`
(balances speed vs memory - 3 concurrent tabs use ~900 MB, well within 2048 MB).
