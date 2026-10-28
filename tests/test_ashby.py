from datetime import datetime, timezone

import pytest

from scrapers import ashby

BOARD = "https://jobs.ashbyhq.com/example"

DATA = {
    "jobs": [
        {
            "id": "job-123",
            "title": "Quality Analyst",
            "jobUrl": "https://jobs.ashbyhq.com/example/job-123",
            "location": "Toronto Office",
            "workplaceType": "Hybrid",
            "isRemote": True,
            "employmentType": "FullTime",
            "publishedAt": "2026-10-15T15:43:30.129+00:00",
            "isListed": True,
            "descriptionHtml": "<p>Build <strong>reliable</strong> systems.</p><ul><li>Test them.</li></ul>",
        },
        {
            "id": "job-hidden",
            "title": "Unlisted Analyst",
            "isListed": False,
        },
        {
            "id": "job-456",
            "title": "Business Analyst",
        },
    ]
}


def test_parse_board_slug_accepts_board_and_job_paths():
    assert ashby.parse_board_slug(BOARD) == "example"
    assert ashby.parse_board_slug(f"{BOARD}/job-123") == "example"


def test_parse_board_slug_rejects_non_ashby_host():
    with pytest.raises(ValueError, match="Expected an Ashby"):
        ashby.parse_board_slug("https://example.com/jobs")


def test_parse_jobs_extracts_list_fields_and_skips_unlisted_jobs():
    first, second = ashby.parse_jobs(DATA, BOARD)

    assert first.source_job_id == "job-123"
    assert first.title == "Quality Analyst"
    assert first.url == "https://jobs.ashbyhq.com/example/job-123"
    assert first.location == "Toronto Office"
    assert first.work_mode == "Hybrid"
    assert first.employment_type == "Full-time"
    assert first.posted_at == datetime(2026, 10, 15, 15, 43, 30, 129000, tzinfo=timezone.utc)
    assert "Build" in first.description
    assert "Test them." in first.description
    assert "<p>" not in first.description
    assert second.url == "https://jobs.ashbyhq.com/example/job-456"


def test_parse_jobs_rejects_invalid_response_and_cross_board_urls():
    with pytest.raises(ValueError, match="missing its jobs list"):
        ashby.parse_jobs({}, BOARD)
    with pytest.raises(ValueError, match="does not match the board"):
        ashby.parse_jobs({
            "jobs": [{
                "id": "job-1",
                "title": "Analyst",
                "jobUrl": "https://jobs.ashbyhq.com/other/job-1",
            }]
        }, BOARD)


def test_fetch_detail_is_empty_when_list_already_contains_details():
    assert ashby.fetch_detail(BOARD, object()) == {}
