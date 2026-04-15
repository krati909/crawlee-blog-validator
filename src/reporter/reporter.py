"""
src/reporter/reporter.py
-------------------------
Generates structured reports from ValidationResult objects.

Two output formats:
  1. JSON  - machine-readable, suitable for CI/CD pipelines, dashboards,
             Slack/email notifications, and further programmatic analysis.
  2. HTML  - self-contained, human-readable report with colour-coded rows.
             Designed for both technical and non-technical stakeholders.

Both files are written to REPORT_OUTPUT_DIR and the paths are returned
so that callers (e.g., the Lambda handler) can attach them to a response.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import REPORT_INCLUDE_NORMALIZED, REPORT_OUTPUT_DIR
from src.validator.validator import ValidationResult, ValidationStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Summary dataclass
# ---------------------------------------------------------------------------


class ReportSummary:
    """Aggregated counts computed from a list of ValidationResults."""

    def __init__(self, results: list[ValidationResult]) -> None:
        self.total = len(results)
        self.matched = sum(1 for r in results if r.status == ValidationStatus.MATCH)
        self.truncated = sum(1 for r in results if r.status == ValidationStatus.TRUNCATED)
        self.fuzzy = sum(1 for r in results if r.status == ValidationStatus.FUZZY_MATCH)
        self.mismatched = sum(1 for r in results if r.status == ValidationStatus.MISMATCH)
        self.errors = sum(1 for r in results if r.status == ValidationStatus.ERROR)
        self.skipped = sum(1 for r in results if r.status == ValidationStatus.SKIPPED)
        self.passing = sum(1 for r in results if r.status.is_passing)
        self.failing = self.total - self.passing
        self.pass_rate = (
            f"{self.passing / self.total * 100:.1f}%" if self.total else "N/A"
        )

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "matched": self.matched,
            "truncated": self.truncated,
            "fuzzy_match": self.fuzzy,
            "mismatched": self.mismatched,
            "errors": self.errors,
            "skipped": self.skipped,
            "passing": self.passing,
            "failing": self.failing,
            "pass_rate": self.pass_rate,
        }


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class Reporter:
    """
    Writes JSON and HTML reports to disk and returns their paths.

    Usage:
        summary, json_path, html_path = Reporter().generate(results)
    """

    def generate(
        self,
        results: list[ValidationResult],
        run_id: Optional[str] = None,
    ) -> tuple[ReportSummary, str, str]:
        """
        Generate both report formats.

        Args:
            results : validated results from Validator
            run_id  : optional identifier; defaults to ISO-8601 UTC timestamp

        Returns:
            (summary, json_path, html_path)
        """
        run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        summary = ReportSummary(results)

        output_dir = Path(REPORT_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = self._write_json(results, summary, run_id, output_dir)
        html_path = self._write_html(results, summary, run_id, output_dir)

        logger.info("Reports written → %s | %s", json_path, html_path)
        return summary, json_path, html_path

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _write_json(
        self,
        results: list[ValidationResult],
        summary: ReportSummary,
        run_id: str,
        output_dir: Path,
    ) -> str:
        path = output_dir / f"report_{run_id}.json"

        report = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_url": "https://crawlee.dev/blog",
            "summary": summary.to_dict(),
            "results": [self._result_to_dict(r) for r in results],
        }

        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def _result_to_dict(self, r: ValidationResult) -> dict:
        d = {
            "position": r.position,
            "status": r.status.value,
            "menu_label": r.menu_label,
            "article_title": r.article_title,
            "url": r.url,
        }
        if r.error:
            d["error"] = r.error
        if r.note:
            d["note"] = r.note
        if r.similarity_score is not None:
            d["similarity_score"] = r.similarity_score
        if REPORT_INCLUDE_NORMALIZED:
            d["normalized_label"] = r.normalized_label
            d["normalized_title"] = r.normalized_title
        return d

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _write_html(
        self,
        results: list[ValidationResult],
        summary: ReportSummary,
        run_id: str,
        output_dir: Path,
    ) -> str:
        path = output_dir / f"report_{run_id}.html"
        path.write_text(self._build_html(results, summary, run_id), encoding="utf-8")
        return str(path)

    def _build_html(
        self,
        results: list[ValidationResult],
        summary: ReportSummary,
        run_id: str,
    ) -> str:
        rows_html = "\n".join(self._result_row(r) for r in results)
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Crawlee Blog Validator - Report {run_id}</title>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --border: #2e3147;
      --text: #e2e8f0;
      --muted: #8892a4;
      --match: #22c55e;
      --match-bg: #052e16;
      --truncated: #3b82f6;
      --truncated-bg: #0c1a3a;
      --fuzzy: #a855f7;
      --fuzzy-bg: #1e0a3a;
      --mismatch: #ef4444;
      --mismatch-bg: #2d0707;
      --error: #f97316;
      --error-bg: #2d1200;
      --skipped: #94a3b8;
      --skipped-bg: #1e2535;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 2rem;
    }}
    header {{ margin-bottom: 2rem; }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    header p {{ color: var(--muted); margin-top: 0.3rem; font-size: 0.9rem; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      text-align: center;
    }}
    .stat-card .value {{ font-size: 2rem; font-weight: 700; }}
    .stat-card .label {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.2rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .stat-card.pass .value {{ color: var(--match); }}
    .stat-card.fail .value {{ color: var(--mismatch); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    thead tr {{ background: var(--surface); }}
    th {{ padding: 0.75rem 1rem; text-align: left; font-weight: 600; color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); }}
    td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{
      display: inline-block;
      padding: 0.2em 0.7em;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.04em;
    }}
    .badge-MATCH      {{ background: var(--match-bg);    color: var(--match);    }}
    .badge-TRUNCATED  {{ background: var(--truncated-bg); color: var(--truncated); }}
    .badge-FUZZY_MATCH{{ background: var(--fuzzy-bg);    color: var(--fuzzy);    }}
    .badge-MISMATCH   {{ background: var(--mismatch-bg); color: var(--mismatch); }}
    .badge-ERROR      {{ background: var(--error-bg);    color: var(--error);    }}
    .badge-SKIPPED    {{ background: var(--skipped-bg);  color: var(--skipped);  }}
    .url-cell a {{ color: var(--muted); text-decoration: none; font-size: 0.8rem; }}
    .url-cell a:hover {{ color: var(--text); }}
    .note {{ font-size: 0.8rem; color: var(--muted); margin-top: 0.25rem; }}
    .error-text {{ color: var(--error); font-size: 0.8rem; }}
    footer {{ margin-top: 2rem; color: var(--muted); font-size: 0.8rem; text-align: center; }}
  </style>
</head>
<body>
  <header>
    <h1>🔍 Crawlee Blog Validator - Test Report</h1>
    <p>Target: <a href="https://crawlee.dev/blog" style="color: var(--muted)">https://crawlee.dev/blog</a>
       &nbsp;|&nbsp; Run ID: {run_id}
       &nbsp;|&nbsp; Generated: {generated_at}
    </p>
  </header>

  <div class="summary-grid">
    <div class="stat-card">
      <div class="value">{summary.total}</div>
      <div class="label">Total</div>
    </div>
    <div class="stat-card pass">
      <div class="value">{summary.pass_rate}</div>
      <div class="label">Pass Rate</div>
    </div>
    <div class="stat-card pass">
      <div class="value">{summary.matched}</div>
      <div class="label">Matched</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:var(--truncated)">{summary.truncated}</div>
      <div class="label">Truncated</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:var(--fuzzy)">{summary.fuzzy}</div>
      <div class="label">Fuzzy Match</div>
    </div>
    <div class="stat-card fail">
      <div class="value">{summary.mismatched}</div>
      <div class="label">Mismatched</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:var(--error)">{summary.errors}</div>
      <div class="label">Errors</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Status</th>
        <th>Menu Label</th>
        <th>Article Title</th>
        <th>URL</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  <footer>
    Generated by Crawlee Blog Validator &nbsp;|&nbsp;
    <a href="https://github.com/apify/crawlee-python" style="color: inherit">crawlee-python</a>
  </footer>
</body>
</html>"""

    @staticmethod
    def _result_row(r: ValidationResult) -> str:
        status_badge = (
            f'<span class="badge badge-{r.status.value}">{r.status.value}</span>'
        )

        note_html = ""
        if r.note:
            note_html = f'<div class="note">{r.note}</div>'
        if r.error:
            note_html = f'<div class="error-text">{r.error}</div>'

        title_cell = r.article_title or '<span style="color:var(--muted)">-</span>'

        return f"""<tr>
  <td>{r.position}</td>
  <td>{status_badge}</td>
  <td>{r.menu_label}{note_html}</td>
  <td>{title_cell}</td>
  <td class="url-cell"><a href="{r.url}" target="_blank" rel="noopener">↗ link</a></td>
</tr>"""
