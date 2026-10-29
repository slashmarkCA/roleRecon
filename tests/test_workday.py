from unittest.mock import Mock
from datetime import timezone

from scrapers import workday

BOARD = "https://example.wd3.myworkdayjobs.com/en-US/Careers"


def test_parse_board_url():
    b = workday.parse_board_url(BOARD)
    assert b["tenant"] == "example" and b["site"] == "Careers" and b["locale"] == "en-US"
    assert b["api_base"] == "https://example.wd3.myworkdayjobs.com/wday/cxs/example/Careers"


def test_parse_board_url_without_locale():
    b = workday.parse_board_url("https://acme.wd3.myworkdayjobs.com/Careers")
    assert b["tenant"] == "acme" and b["site"] == "Careers" and b["locale"] == "en-US"


def test_parse_board_url_from_a_single_job_link():
    # A pasted link to one job: the board is the part before /details/
    b = workday.parse_board_url(
        "https://acme.wd3.myworkdayjobs.com/en-US/Careers/details/Business-Analyst_JR100?locations=abc")
    assert b["tenant"] == "acme" and b["site"] == "Careers" and b["locale"] == "en-US"


def test_parse_board_url_with_query_and_no_locale():
    b = workday.parse_board_url("https://acme.wd3.myworkdayjobs.com/Careers?jobFamilyGroup=abc&jobFamilyGroup=def")
    assert b["tenant"] == "acme" and b["site"] == "Careers" and b["locale"] == "en-US"
    assert b["applied_facets"] == {"jobFamilyGroup": ["abc", "def"]}


def test_search_payload_pages_with_offset():
    payload = workday.build_search_payload(offset=40)
    assert payload["offset"] == 40 and payload["limit"] == workday.PAGE_SIZE


def test_search_payload_includes_applied_facets_and_query():
    payload = workday.build_search_payload(
        query="analyst",
        applied_facets={"locationCountry": ["canada-id"]},
    )
    assert payload["searchText"] == "analyst"
    assert payload["appliedFacets"] == {"locationCountry": ["canada-id"]}


def test_parse_board_url_extracts_repeated_facets_and_search_text():
    board = workday.parse_board_url(
        "https://acme.wd3.myworkdayjobs.com/Careers"
        "?locationCountry=canada-id&locationCountry=us-id&searchText=analyst"
    )
    assert board["applied_facets"] == {
        "locationCountry": ["canada-id", "us-id"],
    }
    assert board["search_text"] == "analyst"


def test_fetch_list_passes_board_facets_to_workday_api():
    response = Mock()
    response.json.return_value = {"total": 0, "jobPostings": []}
    session = Mock()
    session.post.return_value = response
    board = (
        "https://example.wd3.myworkdayjobs.com/Careers"
        "?locationCountry=canada-id"
    )

    assert workday.fetch_list(board, session=session) == []
    assert session.post.call_args.kwargs["json"]["appliedFacets"] == {
        "locationCountry": ["canada-id"],
    }


def test_parse_search_results_skips_entries_without_a_path():
    data = {
        "total": 2,
        "jobPostings": [
            {"title": "QA Analyst", "externalPath": "/job/Toronto/QA-Analyst_R1", "locationsText": "Toronto"},
            {"title": "Promo tile without a link"},
        ],
    }
    (job,) = workday.parse_search_results(data, BOARD)
    assert job.title == "QA Analyst" and job.location == "Toronto"
    assert job.source_job_id == "/job/Toronto/QA-Analyst_R1"
    assert job.url == "https://example.wd3.myworkdayjobs.com/en-US/Careers/job/Toronto/QA-Analyst_R1"


def test_parse_detail():
    data = {"jobPostingInfo": {
        "jobDescription": "<p>Hello <b>world</b></p>",
        "location": "Toronto",
        "additionalLocations": ["Remote"],
        "timeType": "Full time",
        "startDate": "2026-01-02",
    }}
    detail = workday.parse_detail(data)
    assert "Hello" in detail["description"] and "<" not in detail["description"]
    assert detail["location"] == "Toronto; Remote"
    assert detail["employment_type"] == "Full time"
    assert detail["posted_at"].tzinfo == timezone.utc
