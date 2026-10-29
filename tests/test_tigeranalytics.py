import pytest

from scrapers import tigeranalytics
from scrapers.base import JobRecord

BOARD = "https://www.tigeranalytics.com/about-us/current-openings/"

CAREERS_PAGE = """<html><body>
<div class="results">
  <div class="row all-jobs-list-wrap">
    <div class="jobs-title">Data Analyst - Toronto</div>
    <div class="jobs-location">CA</div>
    <div class="jobs-apply"><a href="https://apply.workable.com/j/ABC123">Apply now</a></div>
  </div>
  <div class="row all-jobs-list-wrap">
    <div class="jobs-title">Business Analyst - Canada</div>
    <div class="jobs-location">CA</div>
    <div class="jobs-apply"><a href="https://apply.workable.com/j/XYZ789">Apply now</a></div>
  </div>
  <div class="career_pagination" data-jc="CA" data-tj="2" data-tp="1"></div>
</div>
<div class="results">
  <div class="row all-jobs-list-wrap">
    <div class="jobs-title">India role</div>
    <div class="jobs-location">IN</div>
    <div class="jobs-apply"><a href="https://apply.workable.com/j/IND123">Apply now</a></div>
  </div>
  <div class="career_pagination" data-jc="IN" data-tj="1" data-tp="1"></div>
</div>
</body></html>"""

DETAIL = """# Data Analyst - Toronto

> Tiger Analytics Inc. · Toronto, Canada · Full-time · Posted 2026-10-13

**Workplace:** hybrid

## Description

Analyze data and communicate findings.
"""


def test_parse_board_url_accepts_tiger_careers_page():
    assert tigeranalytics.parse_board_url(BOARD) == BOARD
    with pytest.raises(ValueError, match="Expected Tiger Analytics"):
        tigeranalytics.parse_board_url("https://example.com/careers")


def test_parse_job_list_extracts_only_canadian_cards():
    first, second = tigeranalytics.parse_job_list(CAREERS_PAGE, BOARD)

    assert first == JobRecord(
        source_job_id="ABC123",
        url="https://apply.workable.com/j/ABC123",
        title="Data Analyst - Toronto",
        location="Canada",
    )
    assert second.source_job_id == "XYZ789"
    assert second.location == "Canada"


def test_parse_job_list_rejects_missing_canada_results():
    with pytest.raises(ValueError, match="missing its Canada results"):
        tigeranalytics.parse_job_list("<html></html>", BOARD)


def test_parse_job_list_reports_mismatch_between_count_and_cards():
    page = CAREERS_PAGE.replace('data-tj="2"', 'data-tj="3"')
    with pytest.raises(ValueError, match="declared 3 jobs but contained 2"):
        tigeranalytics.parse_job_list(page, BOARD)


def test_parse_detail_reuses_workable_markdown_parser():
    detail = tigeranalytics.parse_detail(DETAIL)
    assert detail["description"] == "Analyze data and communicate findings."
    assert detail["location"] == "Toronto, Canada"


def test_fetch_detail_rejects_unrelated_workable_job_url():
    record = JobRecord("ABC123", "https://apply.workable.com/other/j/ABC123", "Data Analyst")
    with pytest.raises(ValueError, match="does not match the Tiger Analytics board"):
        tigeranalytics.fetch_detail(BOARD, record)
