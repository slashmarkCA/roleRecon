from datetime import datetime, timezone

import pytest

from scrapers import workable

BOARD = "https://apply.workable.com/example/"

LISTING = """# Example — All Open Positions

| Title | Department | Location | Type | Salary | Posted | Details |
|-------|-----------|----------|------|--------|--------|---------|
| Business Analyst | Consulting | Toronto, Canada (Hybrid) | Full-time | CAD 75,000–85,000 | 2026-10-13 | [View](https://apply.workable.com/example/jobs/view/ABC123.md) |
| Support Engineer | R&D | Auckland, New Zealand | — | — | — | [View](https://apply.workable.com/example/jobs/view/XYZ789.md) |
| Broken row | Consulting | Toronto | Full-time | — | — | no link |
"""

DETAIL = """# Business Analyst

> Example Corp · Toronto, Canada (Hybrid) · Full-time · Posted 2026-10-13

**Salary:** CAD 75,000–85,000

**Workplace:** hybrid

**Department:** Consulting

## Description

We need an experienced **Business Analyst**.

**What you’ll do**

- Gather requirements.
- Work with [engineering teams](https://example.com/teams).

## About Example
Other information.
"""


def test_parse_board_url_accepts_board_and_job_page_paths():
    board = workable.parse_board_url("https://apply.workable.com/example/jobs/view/123")
    assert board["slug"] == "example"
    assert board["board_url"] == BOARD
    assert board["list_url"] == "https://apply.workable.com/example/jobs.md"


def test_parse_board_url_preserves_search_filters_for_the_list_request():
    board = workable.parse_board_url(
        "https://apply.workable.com/example/?lng=en"
        "&location%5B0%5D%5Bcountry%5D=Canada"
        "&location%5B0%5D%5Bregion%5D=Ontario"
    )
    assert board["list_url"] == (
        "https://apply.workable.com/example/jobs.md?lng=en"
        "&location%5B0%5D%5Bcountry%5D=Canada"
        "&location%5B0%5D%5Bregion%5D=Ontario"
    )


def test_parse_board_url_rejects_non_workable_host():
    with pytest.raises(ValueError, match="Expected a Workable"):
        workable.parse_board_url("https://example.com/jobs")


def test_parse_job_list_extracts_records_and_skips_invalid_rows():
    first, second = workable.parse_job_list(LISTING, BOARD)

    assert first.source_job_id == "ABC123"
    assert first.title == "Business Analyst"
    assert first.location == "Toronto, Canada"
    assert first.work_mode == "Hybrid"
    assert first.employment_type == "Full-time"
    assert first.salary_text == "CAD 75,000–85,000"
    assert first.posted_at == datetime(2026, 10, 13, tzinfo=timezone.utc)
    assert first.url == "https://apply.workable.com/example/jobs/view/ABC123.md"

    assert second.title == "Support Engineer"
    assert second.location == "Auckland, New Zealand"
    assert second.work_mode == ""
    assert second.employment_type == ""
    assert second.salary_text == ""
    assert second.posted_at is None


def test_parse_job_list_rejects_detail_links_from_other_accounts():
    markdown = LISTING.replace(
        "https://apply.workable.com/example/jobs/view/ABC123.md",
        "https://apply.workable.com/other/jobs/view/ABC123.md",
    )
    records = workable.parse_job_list(markdown, BOARD)
    assert [record.source_job_id for record in records] == ["XYZ789"]


def test_parse_job_list_rejects_unrecognized_response():
    with pytest.raises(ValueError, match="missing the expected jobs table"):
        workable.parse_job_list("<html>Unexpected response</html>", BOARD)


def test_parse_job_detail_returns_plain_text_and_fields():
    detail = workable.parse_job_detail(DETAIL)

    assert detail["description"] == (
        "We need an experienced Business Analyst.\n\n"
        "What you’ll do\n"
        "- Gather requirements.\n"
        "- Work with engineering teams."
    )
    assert detail["location"] == "Toronto, Canada"
    assert detail["work_mode"] == "Hybrid"
    assert detail["employment_type"] == "Full-time"
    assert detail["salary_text"] == "CAD 75,000–85,000"
    assert detail["posted_at"] == datetime(2026, 10, 13, tzinfo=timezone.utc)
    assert detail["title"] == "Business Analyst"


def test_parse_job_detail_normalizes_workable_on_site_value():
    markdown = DETAIL.replace("**Workplace:** hybrid", "**Workplace:** on_site")
    assert workable.parse_job_detail(markdown)["work_mode"] == "On-site"


def test_parse_job_detail_rejects_missing_description():
    with pytest.raises(ValueError, match="missing its description"):
        workable.parse_job_detail("# Business Analyst\n\nNo description section.")
