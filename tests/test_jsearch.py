import pytest

from scrapers import jsearch


SAMPLE = {
    "data": [
        {
            "job_id": "job-1",
            "job_title": "Business Analyst",
            "job_apply_link": "https://jobs.example/jobs/1",
            "employer_name": "Example Bank",
            "job_city": "Toronto",
            "job_state": "ON",
            "job_country": "Canada",
            "job_is_remote": False,
            "job_employment_types": ["FULLTIME"],
            "job_posted_at_datetime_utc": "2026-10-30T12:00:00Z",
            "job_description": "<p>Build <strong>useful</strong> systems &amp; tools.</p>",
        },
        {
            "job_id": "job-2",
            "title": "Remote Analyst",
            "job_google_link": "https://google.example/jobs/2",
            "company": {"display_name": "Sample Co"},
            "location": {"display_name": "Remote • Canada"},
            "remote": True,
            "job_description": "Plain-text description",
        },
    ],
    "cursor": "next-page",
}


def test_parse_search_results_maps_job_fields_and_cleans_description():
    first, second = jsearch.parse_search_results(SAMPLE)

    assert first.source_job_id == "job-1"
    assert first.title == "Business Analyst"
    assert first.url == "https://jobs.example/jobs/1"
    assert first.company == "Example Bank"
    assert first.location == "Toronto, ON, Canada"
    assert first.employment_type == "FULLTIME"
    assert first.posted_at.isoformat() == "2026-10-30T12:00:00+00:00"
    assert first.description == "Build\nuseful\nsystems & tools."
    assert second.url == "https://google.example/jobs/2"
    assert second.company == "Sample Co"
    assert second.location == "Remote • Canada"
    assert second.work_mode == "Remote"


def test_parse_search_results_deduplicates_repeated_job_ids():
    payload = {"data": [SAMPLE["data"][0], SAMPLE["data"][0]]}

    assert len(jsearch.parse_search_results(payload)) == 1


def test_parse_search_results_deduplicates_same_url_with_different_ids():
    duplicate = {**SAMPLE["data"][0], "job_id": "job-duplicate"}
    assert len(jsearch.parse_search_results({"data": [SAMPLE["data"][0], duplicate]})) == 1


def test_parse_search_results_rejects_malformed_records():
    with pytest.raises(ValueError, match="title or application URL"):
        jsearch.parse_search_results({"data": [{"job_id": "missing-fields"}]})


def test_fetch_list_uses_api_key_options_and_deduplicates_queries(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return SAMPLE

    class Session:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    monkeypatch.setenv("OPENWEBNINJA_API_KEY", "test-key")
    records = jsearch.fetch_list(
        "https://api.openwebninja.com/jsearch/search-v2",
        session=session,
        options={"queries": ["analyst Toronto", "business analyst Ontario"], "max_pages": 2},
    )

    assert len(records) == 2
    assert len(session.calls) == 2
    assert session.calls[0][1]["params"] == {
        "query": "analyst Toronto",
        "country": "ca",
        "num_pages": 2,
        "date_posted": "month",
    }
    assert session.calls[0][1]["headers"]["x-api-key"] == "test-key"


def test_fetch_list_refuses_a_request_budget_over_the_per_scrape_limit(monkeypatch):
    monkeypatch.setenv("OPENWEBNINJA_API_KEY", "test-key")
    with pytest.raises(ValueError, match="per-scrape limit"):
        jsearch.fetch_list(
            "",
            options={
                "queries": [f"query {index}" for index in range(11)],
                "max_pages": 3,
            },
        )


def test_fetch_list_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENWEBNINJA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENWEBNINJA_API_KEY is not set"):
        jsearch.fetch_list("", options={"queries": ["analyst Toronto"]})
