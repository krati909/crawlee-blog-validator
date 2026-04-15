"""
tests/test_reporter.py
-----------------------
Unit tests for the Reporter: summary calculation and file output.

These tests do NOT require a browser.  They write files to a temp directory
that pytest cleans up automatically.
"""

import json
import os
from pathlib import Path

import pytest

from src.reporter.reporter import Reporter, ReportSummary
from src.validator.validator import ValidationResult, ValidationStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_result(status: ValidationStatus, pos: int = 1) -> ValidationResult:
    return ValidationResult(
        status=status,
        menu_label=f"Post {pos}",
        article_title=f"Article {pos}" if status != ValidationStatus.ERROR else None,
        url=f"https://crawlee.dev/blog/post-{pos}",
        position=pos,
        error="Some error" if status == ValidationStatus.ERROR else None,
    )


@pytest.fixture
def mixed_results() -> list[ValidationResult]:
    return [
        make_result(ValidationStatus.MATCH,      pos=1),
        make_result(ValidationStatus.MATCH,      pos=2),
        make_result(ValidationStatus.TRUNCATED,  pos=3),
        make_result(ValidationStatus.FUZZY_MATCH,pos=4),
        make_result(ValidationStatus.MISMATCH,   pos=5),
        make_result(ValidationStatus.ERROR,      pos=6),
    ]


# ---------------------------------------------------------------------------
# ReportSummary
# ---------------------------------------------------------------------------


class TestReportSummary:

    def test_counts(self, mixed_results):
        s = ReportSummary(mixed_results)
        assert s.total     == 6
        assert s.matched   == 2
        assert s.truncated == 1
        assert s.fuzzy     == 1
        assert s.mismatched== 1
        assert s.errors    == 1

    def test_passing_and_failing(self, mixed_results):
        s = ReportSummary(mixed_results)
        # MATCH + TRUNCATED + FUZZY_MATCH = 4 passing
        assert s.passing == 4
        assert s.failing == 2

    def test_pass_rate(self, mixed_results):
        s = ReportSummary(mixed_results)
        assert s.pass_rate == "66.7%"

    def test_empty_results(self):
        s = ReportSummary([])
        assert s.total == 0
        assert s.pass_rate == "N/A"

    def test_to_dict_keys(self, mixed_results):
        d = ReportSummary(mixed_results).to_dict()
        expected_keys = {
            "total", "matched", "truncated", "fuzzy_match",
            "mismatched", "errors", "skipped", "passing", "failing", "pass_rate",
        }
        assert expected_keys == set(d.keys())


# ---------------------------------------------------------------------------
# Reporter - file output
# ---------------------------------------------------------------------------


class TestReporter:

    def test_generates_json_file(self, mixed_results, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path))
        # Re-import settings to pick up monkeypatched env var
        import importlib
        import config.settings as settings
        importlib.reload(settings)
        # Patch the module-level constant directly
        import src.reporter.reporter as reporter_mod
        reporter_mod.REPORT_OUTPUT_DIR = str(tmp_path)

        reporter = Reporter()
        _, json_path, _ = reporter.generate(mixed_results, run_id="test123")

        assert Path(json_path).exists()

    def test_json_structure(self, mixed_results, tmp_path, monkeypatch):
        import src.reporter.reporter as reporter_mod
        reporter_mod.REPORT_OUTPUT_DIR = str(tmp_path)

        reporter = Reporter()
        _, json_path, _ = reporter.generate(mixed_results, run_id="test123")

        data = json.loads(Path(json_path).read_text())
        assert data["run_id"] == "test123"
        assert "summary" in data
        assert "results" in data
        assert len(data["results"]) == len(mixed_results)

    def test_generates_html_file(self, mixed_results, tmp_path):
        import src.reporter.reporter as reporter_mod
        reporter_mod.REPORT_OUTPUT_DIR = str(tmp_path)

        reporter = Reporter()
        _, _, html_path = reporter.generate(mixed_results, run_id="test123")

        html = Path(html_path).read_text()
        assert "<!DOCTYPE html>" in html

    def test_html_contains_all_statuses(self, mixed_results, tmp_path):
        import src.reporter.reporter as reporter_mod
        reporter_mod.REPORT_OUTPUT_DIR = str(tmp_path)

        reporter = Reporter()
        _, _, html_path = reporter.generate(mixed_results, run_id="test123")

        html = Path(html_path).read_text()
        for status in [
            "MATCH", "TRUNCATED", "FUZZY_MATCH", "MISMATCH", "ERROR"
        ]:
            assert status in html, f"Status '{status}' missing from HTML report"

    def test_json_result_has_required_fields(self, mixed_results, tmp_path):
        import src.reporter.reporter as reporter_mod
        reporter_mod.REPORT_OUTPUT_DIR = str(tmp_path)

        reporter = Reporter()
        _, json_path, _ = reporter.generate(mixed_results, run_id="test123")

        data = json.loads(Path(json_path).read_text())
        for item in data["results"]:
            assert "position" in item
            assert "status"   in item
            assert "menu_label" in item
            assert "url"      in item
