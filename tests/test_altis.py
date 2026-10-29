from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from scrapers import altis
from scrapers.base import JobRecord

BOARD = "https://jobportal.altis.com/"

SUMMARY = {
    "jobId": 12345,
    "jobType": "Permanent",
    "jobTitle": "Business Analyst",
    "datePosted": "10/28/2026 12:00:00 AM",
    "location": "Toronto, ON",
    "jobDescription": "<p>Short summary.</p>",
    "availabilityTypeId": "Hybrid",
    "salaryFrom": "75,000",
    "salaryTo": "85,000",
    "salaryPer": "per Year",
}

DETAIL = {
    **SUMMARY,
    "jobDescription": (
        "<div><p>Gather requirements.</p><script>not job content</script>"
        "<p>Collaborate with delivery teams.</p></div>"
    ),
}


def test_parse_board_url_accepts_portal_root_only():
    assert altis.parse_board_url(BOARD) == {
        "search_url": "https://apis.altisexcel.com/Applicant/jobs/ads/Search",
        "locations": [],
    }
    assert altis.parse_board_url(
        "https://jobportal.altis.com/?location=Toronto%2C+ON&location=Oshawa%2C+ON"
    ) == {
        "search_url": "https://apis.altisexcel.com/Applicant/jobs/ads/Search",
        "locations": ["Toronto, ON", "Oshawa, ON"],
    }
    with pytest.raises(ValueError, match="Expected the Altis job portal"):
        altis.parse_board_url("https://example.com/")
    with pytest.raises(ValueError, match="Expected the Altis job portal"):
        altis.parse_board_url("https://jobportal.altis.com/jobs/123")


def test_build_search_payload_supports_location_filter_values():
    payload = altis.build_search_payload(["Toronto, ON", "Oshawa, ON"])
    assert payload["locations"] == ["Toronto, ON", "Oshawa, ON"]
    assert payload["keyword"] is None
    assert payload["jobTypeIds"] == []


def test_parse_job_list_extracts_fields_and_builds_public_job_url():
    (record,) = altis.parse_job_list([SUMMARY], BOARD)
    assert record == JobRecord(
        source_job_id="12345",
        url="https://jobportal.altis.com/jobs/12345",
        title="Business Analyst",
        location="Toronto, ON",
        work_mode="Hybrid",
        employment_type="Permanent",
        salary_text="75,000-85,000 per Year",
        posted_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    assert record.description == ""


def test_parse_job_list_rejects_invalid_response_shapes():
    with pytest.raises(ValueError, match="is not a list"):
        altis.parse_job_list({"jobs": []}, BOARD)
    with pytest.raises(ValueError, match="missing its id or title"):
        altis.parse_job_list([{"jobId": 1}], BOARD)
    with pytest.raises(ValueError, match="id is not numeric"):
        altis.parse_job_list([{"jobId": "abc", "jobTitle": "Analyst"}], BOARD)


def test_parse_job_detail_extracts_plain_description_and_fields():
    detail = altis.parse_job_detail(DETAIL)
    assert detail == {
        "description": "Gather requirements.\nCollaborate with delivery teams.",
        "location": "Toronto, ON",
        "work_mode": "Hybrid",
        "employment_type": "Permanent",
        "salary_text": "75,000-85,000 per Year",
        "posted_at": datetime(2026, 10, 28, tzinfo=timezone.utc),
        "title": "Business Analyst",
    }


def test_parse_job_detail_rejects_missing_description():
    with pytest.raises(ValueError, match="missing its description"):
        altis.parse_job_detail({**SUMMARY, "jobDescription": ""})


def test_fetch_list_posts_public_search_payload():
    response = Mock()
    response.json.return_value = [SUMMARY]
    session = Mock()
    session.post.return_value = response

    records = altis.fetch_list(BOARD, session=session)

    assert records[0].source_job_id == "12345"
    assert session.post.call_args.args[0] == (
        "https://apis.altisexcel.com/Applicant/jobs/ads/Search"
    )
    assert session.post.call_args.kwargs["json"] == altis.build_search_payload()


def test_fetch_list_uses_location_filters_from_board_url():
    response = Mock()
    response.json.return_value = [SUMMARY]
    session = Mock()
    session.post.return_value = response
    board = "https://jobportal.altis.com/?location=Toronto%2C+ON"

    altis.fetch_list(board, session=session)

    assert session.post.call_args.kwargs["json"]["locations"] == ["Toronto, ON"]


def test_fetch_detail_rejects_unrelated_or_mismatched_posting_urls():
    record = JobRecord("12345", "https://example.com/jobs/12345", "Analyst")
    with pytest.raises(ValueError, match="does not match the requested posting"):
        altis.fetch_detail(BOARD, record)

    record.url = "https://jobportal.altis.com/jobs/67890"
    with pytest.raises(ValueError, match="does not match the requested posting"):
        altis.fetch_detail(BOARD, record)
