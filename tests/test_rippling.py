import json
from datetime import datetime, timezone

import pytest

from scrapers import rippling

BOARD = "https://ats.rippling.com/en-CA/example/jobs"


def _page(props):
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": props}})
        + "</script></body></html>"
    )


def _list_page(items):
    return _page({
        "apiData": {"jobBoardSlug": "example"},
        "dehydratedState": {
            "queries": [{
                "queryKey": ["board", "example", "job-posts", True, {"page": 0}],
                "state": {"data": {"items": items, "page": 0, "pageSize": 1000}},
            }],
        },
    })


def test_parse_board_url_preserves_locale_and_requests_large_page():
    assert rippling.parse_board_url(BOARD) == {
        "slug": "example",
        "path_prefix": "/en-CA/example",
        "list_url": "https://ats.rippling.com/en-CA/example/jobs?pageSize=1000",
    }


def test_parse_board_url_accepts_board_without_locale_and_rejects_other_hosts():
    assert rippling.parse_board_url("https://ats.rippling.com/example/jobs")["slug"] == "example"
    with pytest.raises(ValueError, match="Expected a Rippling"):
        rippling.parse_board_url("https://example.com/jobs")


def test_parse_job_list_extracts_summaries_and_location_modes():
    page = _list_page([
        {
            "id": "job-123",
            "name": "Platform QA Specialist",
            "locations": [{"name": "Whitby, Canada", "workplaceType": "ON_SITE"}],
        },
        {
            "id": "job-456",
            "name": "Data Analyst",
            "locations": ["Remote (Canada)"],
        },
    ])

    first, second = rippling.parse_job_list(page, BOARD)

    assert first.source_job_id == "job-123"
    assert first.url == "https://ats.rippling.com/en-CA/example/jobs/job-123"
    assert first.title == "Platform QA Specialist"
    assert first.location == "Whitby, Canada"
    assert first.work_mode == "On-site"
    assert second.location == "Remote (Canada)"


def test_parse_job_list_rejects_missing_or_mismatched_page_data():
    with pytest.raises(ValueError, match="missing its Next.js page data"):
        rippling.parse_job_list("<html></html>", BOARD)
    with pytest.raises(ValueError, match="does not match the requested board"):
        rippling.parse_job_list(_list_page([]), "https://ats.rippling.com/en-CA/other/jobs")


def test_parse_job_detail_extracts_description_and_posting_fields():
    page = _page({
        "apiData": {
            "jobBoard": {"slug": "example"},
            "jobPost": {
                "description": {
                    "company": "<p>Example company.</p>",
                    "role": "<p>Build reliable tools.</p>",
                },
                "workLocations": ["Whitby, Canada"],
                "employmentType": {"label": "Full-time"},
                "createdOn": "2026-10-15T15:43:30.129+00:00",
                "payRangeDetails": [{"isRemote": False}],
            },
        },
    })

    detail = rippling.parse_job_detail(page, BOARD)

    assert detail["description"] == "Example company.\n\nBuild reliable tools."
    assert detail["location"] == "Whitby, Canada"
    assert detail["employment_type"] == "Full-time"
    assert detail["posted_at"] == datetime(2026, 10, 15, 15, 43, 30, 129000, tzinfo=timezone.utc)


def test_parse_job_detail_uses_remote_flag_and_rejects_empty_description():
    page = _page({
        "apiData": {
            "jobBoard": {"slug": "example"},
            "jobPost": {
                "description": {"role": "<p>Remote work.</p>"},
                "workLocations": [],
                "payRangeDetails": [{"isRemote": True}],
            },
        },
    })
    assert rippling.parse_job_detail(page, BOARD)["work_mode"] == "Remote"

    empty_page = _page({
        "apiData": {
            "jobBoard": {"slug": "example"},
            "jobPost": {"description": {"role": ""}},
        },
    })
    with pytest.raises(ValueError, match="empty description"):
        rippling.parse_job_detail(empty_page, BOARD)
