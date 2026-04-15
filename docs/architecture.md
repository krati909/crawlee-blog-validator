# Architecture Notes

## Pipeline Overview

```
lambda_handler.py
      │
      ▼
orchestrator.py          ← coordinates stages, logs summary
      │
      ├──[Stage 1]──► crawler.py        ← Phase 1: scrape index
      │                                 ← Phase 2: scrape articles
      │                returns: (menu_entries, article_map)
      │
      ├──[Stage 2]──► validator.py      ← compare + normalise
      │                returns: [ValidationResult, ...]
      │
      └──[Stage 3]──► reporter.py       ← write JSON + HTML
                       returns: (summary, json_path, html_path)
```

---

## Crawler Design (Two-Phase)

### Why two phases instead of one?

A single-phase crawler could navigate to the index, click each link, and
extract both the menu label and the article title in one pass.  However:

- **Separation of concerns**: phase 1 produces a pure list of `(label, url)`
  pairs; phase 2 is a simple batch fetch.  Each phase is independently
  testable and debuggable.
- **Retry granularity**: if an article page fails, Crawlee retries just that
  request - we don't lose the rest of the crawl.
- **Selector failure isolation**: if the index page selector breaks (site
  redesign), the error is immediately obvious and localised to Phase 1.

### Selector cascade

The index-page handler tries four CSS selectors in order of specificity.
This makes the crawler resilient to minor markup changes while documenting
exactly what the code expects from the page structure.

---

## Validator Design (Normalised Comparison)

### Why not `label == title`?

Blog index pages routinely:
- Truncate long titles (sometimes with "…")
- Reformat whitespace (e.g. collapse `\n` from JSX rendering)
- Omit trailing punctuation (colons, question marks)

A strict equality check would produce false mismatches and erode
confidence in the report.

### Status hierarchy

```
MATCH        exact match after normalisation                  ✅ passing
TRUNCATED    label is a prefix of the full title              ✅ passing
FUZZY_MATCH  ≥85% similar (configurable)                     ✅ passing
MISMATCH     labels differ substantially                      ❌ failing
ERROR        page could not be fetched or parsed              ❌ failing
SKIPPED      article URL was not visited by the crawler       ❌ failing
```

TRUNCATED and FUZZY_MATCH are **informational** - they pass by default
because they represent known, acceptable variations.  They are clearly
flagged in the report so a human reviewer can inspect them if desired.

---

## Lambda Deployment Decisions

### Docker image vs zip + layers

| | Zip + Layer | Docker Image |
|---|---|---|
| Max size | 250 MB unzipped | 10 GB |
| Chromium support | Needs custom layer hacks | Native |
| Reproducibility | Layer versioning complexity | Single image tag |
| Cold start | Marginally faster | Slightly slower |

Docker wins for this use case.

### Memory & timeout settings

- **Memory: 1024 MB** - Chromium needs ~400–600 MB under load.  Lambda
  allocates CPU proportional to memory, so more memory also means faster
  execution.
- **Timeout: 300 s** - Crawling 20–30 pages with retries should complete
  in under 2 minutes in practice; 5 minutes gives comfortable headroom.

### /tmp for report output

Lambda functions have 512 MB of ephemeral `/tmp` storage.  Reports
(JSON + HTML) are written there and their paths returned in the Lambda
response.  For production use, the handler could be extended to upload
reports to S3 before returning.

---

## Extension Points

| What | Where | How |
|------|-------|-----|
| Upload reports to S3 | `lambda_handler.py` | Add `boto3.client('s3').upload_file(...)` after `run_pipeline()` |
| Slack/email notification | `orchestrator.py` | Call a notification function after `_log_summary()` |
| Schedule runs (cron) | AWS EventBridge | Add a rule targeting the Lambda function |
| CI/CD integration | `orchestrator.py` | Return non-zero exit code when `summary.failing > 0` |
| Additional pages | `config/settings.py` | Change `BLOG_INDEX_URL` |
