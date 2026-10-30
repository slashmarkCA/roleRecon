from unittest.mock import Mock, call
from datetime import datetime, timezone

import pytest

from scrapers import phenom

BOARD = "https://careers.example.com/us/en/search-results"

SAMPLE = {
    "eagerLoadRefineSearch": {
        "status": 200,
        "hits": 2,
        "totalHits": 2,
        "data": {
            "jobs": [
                {
                    "title": "Digital Solutions Architect",
                    "jobId": "12345",
                    "jobSeqNo": "EXAMPLE12345EXTERNALENUS",
                    "cityStateCountry": "Toronto, Ontario, Canada",
                    "type": "Regular - Full-Time",
                    "postedDate": "2026-10-18T07:00:00.000+0000",
                    "descriptionTeaser": "Design and support digital platforms.",
                },
                {
                    "title": "Food Safety Analyst",
                    "reqId": "23456",
                    "location": "London, Ontario, Canada",
                },
                {"title": "Missing job ID"},
            ],
        },
    },
}


def test_parse_board_url():
    assert phenom.parse_board_url(BOARD) == {
        "origin": "https://careers.example.com",
        "country": "us",
        "lang": "en_us",
        "search_url": "https://careers.example.com/us/en/search-results",
        "job_base": "https://careers.example.com/us/en/job",
    }


def test_build_search_payload_includes_pagination_and_location_filter():
    payload = phenom.build_search_payload(offset=50, limit=25)
    assert payload["ddoKey"] == "eagerLoadRefineSearch"
    assert payload["from"] == 50 and payload["size"] == 25
    assert payload["selected_fields"] == {
        "country": ["Canada"],
        "state": ["Ontario"],
    }


def test_build_search_payload_accepts_custom_location_filters():
    payload = phenom.build_search_payload(
        location_filters={"country": ["Canada"], "city": ["Toronto"]}
    )
    assert payload["selected_fields"] == {
        "country": ["Canada"],
        "city": ["Toronto"],
    }


def test_fetch_list_uses_employer_location_and_pagination_options(monkeypatch):
    first_page = Mock()
    first_page.json.return_value = {
        "eagerLoadRefineSearch": SAMPLE["eagerLoadRefineSearch"] | {
            "totalHits": 4,
            "data": {"jobs": SAMPLE["eagerLoadRefineSearch"]["data"]["jobs"][:2]},
        }
    }
    second_page = Mock()
    second_page.json.return_value = {
        "eagerLoadRefineSearch": SAMPLE["eagerLoadRefineSearch"] | {
            "totalHits": 4,
            "data": {"jobs": SAMPLE["eagerLoadRefineSearch"]["data"]["jobs"][:2]},
        }
    }
    session = Mock()
    session.post.side_effect = [first_page, second_page]
    monkeypatch.setattr(phenom.time, "sleep", lambda _seconds: None)
    options = {
        "phenom": {
            "location": {"country": ["Canada"], "city": ["Toronto"]},
            "page_size": 2,
            "max_jobs": 3,
        }
    }

    records = phenom.fetch_list(BOARD, session=session, options=options)

    assert len(records) == 3
    assert [request.kwargs["json"]["from"] for request in session.post.call_args_list] == [
        0,
        2,
    ]
    assert all(
        request.kwargs["json"]["size"] == 2
        and request.kwargs["json"]["selected_fields"] == {
            "country": ["Canada"],
            "city": ["Toronto"],
        }
        for request in session.post.call_args_list
    )
    assert phenom.list_limit(BOARD, options=options) == 3


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"phenom": {"page_size": 0}}, "page_size.*positive integer"),
        ({"phenom": {"location": {"city": "Toronto"}}}, "city.*list"),
        ({"phenom": {"unknown": True}}, "Unknown Phenom option"),
    ],
)
def test_fetch_list_rejects_invalid_employer_options(options, message):
    with pytest.raises(ValueError, match=message):
        phenom.fetch_list(BOARD, session=Mock(), options=options)


def test_parse_search_results_extracts_standard_job_records():
    first, second = phenom.parse_search_results(SAMPLE, BOARD)

    assert first.source_job_id == "EXAMPLE12345EXTERNALENUS"
    assert first.title == "Digital Solutions Architect"
    assert first.url == (
        "https://careers.example.com/us/en/job/12345/Digital-Solutions-Architect"
    )
    assert first.location == "Toronto, Ontario, Canada"
    assert first.employment_type == "Regular - Full-Time"
    assert first.posted_at == datetime(2026, 10, 18, 7, tzinfo=timezone.utc)
    assert first.description == "Design and support digital platforms."

    assert second.source_job_id == "23456"
    assert second.location == "London, Ontario, Canada"
    assert second.description == ""


def test_parse_search_results_rejects_unsuccessful_response():
    with pytest.raises(ValueError, match="missing successful"):
        phenom.parse_search_results({"status": "failure"}, BOARD)


def test_parse_detail_page_extracts_full_description_from_jobposting_jsonld():
    page = """<html><head>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"JobPosting",
         "datePosted":"2026-10-12",
         "description":"&lt;p&gt;Experience with SQL, Python and Power BI.&lt;/p&gt;"}
      </script>
    </head><body><main>Job posting details</main></body></html>"""

    detail = phenom.parse_detail_page(page)

    assert detail["description"] == "Experience with SQL, Python and Power BI."
    assert detail["posted_at"] == datetime(2026, 10, 12, tzinfo=timezone.utc)


def test_parse_detail_page_rejects_missing_jobposting_data():
    with pytest.raises(ValueError, match="no JobPosting JSON-LD"):
        phenom.parse_detail_page("<html><body>No structured job data</body></html>")
