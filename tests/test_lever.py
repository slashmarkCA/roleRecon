from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from scrapers import lever

BOARD = "https://jobs.lever.co/example"

DATA = [
    {
        "id": "job-123",
        "text": "Data Analyst",
        "hostedUrl": "https://jobs.lever.co/example/job-123",
        "createdAt": 1767225600000,
        "categories": {
            "location": "Toronto, ON",
            "commitment": "Full-time",
        },
        "workplaceType": "hybrid",
        "descriptionPlain": "Analyze business data.",
        "lists": [
            {"text": "What You’ll Do", "content": "<ul><li>Build reports.</li></ul>"},
        ],
        "additionalPlain": "Equal opportunity employer.",
    },
    {"id": "job-456", "text": "Operations Analyst"},
]


def test_parse_board_url_extracts_site_and_api_url():
    board = lever.parse_board_url("https://jobs.lever.co/example/jobs/job-123")
    assert board["site"] == "example"
    assert board["list_url"] == "https://api.lever.co/v0/postings/example"


def test_parse_board_url_rejects_non_lever_urls():
    with pytest.raises(ValueError, match="Expected a Lever"):
        lever.parse_board_url("https://example.com/careers")


def test_parse_jobs_maps_fields_and_combines_description_sections():
    first, second = lever.parse_jobs(DATA, BOARD)

    assert first.source_job_id == "job-123"
    assert first.url == "https://jobs.lever.co/example/job-123"
    assert first.title == "Data Analyst"
    assert first.location == "Toronto, ON"
    assert first.work_mode == "Hybrid"
    assert first.employment_type == "Full-time"
    assert first.posted_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert first.description == (
        "Analyze business data.\n\n"
        "What You’ll Do\nBuild reports.\n\n"
        "Equal opportunity employer."
    )
    assert second.url == "https://jobs.lever.co/example/job-456"
    assert second.description == ""


def test_parse_jobs_rejects_unexpected_response_shape():
    with pytest.raises(ValueError, match="must be a list"):
        lever.parse_jobs({"jobs": []}, BOARD)


def test_parse_jobs_normalizes_on_site_workplace_type():
    posting = {"id": "job-onsite", "workplaceType": "on-site"}
    record = lever.parse_jobs([posting], BOARD)[0]
    assert record.work_mode == "On-site"


def test_fetch_list_requests_the_public_json_postings():
    response = Mock()
    response.json.return_value = DATA
    session = Mock()
    session.get.return_value = response

    records = lever.fetch_list(BOARD, session=session)

    session.get.assert_called_once_with(
        "https://api.lever.co/v0/postings/example",
        params={"mode": "json"},
        headers=lever.UA,
        timeout=30,
    )
    assert len(records) == 2
    assert records[0].title == "Data Analyst"
