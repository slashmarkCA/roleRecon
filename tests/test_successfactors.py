from unittest.mock import Mock, call
from datetime import timezone

import pytest

from scrapers.base import JobRecord
from scrapers import successfactors

BOARD = "https://jobs.example.com/Example/go/Category-Page-Example/123456/"
FEED = "https://jobs.example.com/services/rss/category/?catid=123456"
SEARCH = "https://jobs.example.com/search/?q=&locationsearch=ontario"
OPG_SEARCH = (
    "https://jobs.opg.com/search/?facetFilters=%7B%22jobLocationCity%22%3A%5B%22Oshawa%22%5D%7D"
    "&pageNumber=0"
)

WIDGET_PAGE = """<html><body>
<script>var currentLocale: 'en_GB';</script>
<script>widgetName: 'xweb/rmk-jobs-search'</script>
</body></html>"""

RECRUITING_SAMPLE = {
    "totalJobs": 2,
    "jobSearchResult": [
        {
            "response": {
                "id": "12345",
                "unifiedStandardTitle": "Senior Data Analyst",
                "unifiedUrlTitle": "Senior-Data-Analyst",
                "unifiedStandardStart": "15/10/2026",
                "jobLocationShort": ["Oshawa, ON    "],
            },
        },
        {
            "response": {
                "id": "12346",
                "unifiedStandardTitle": "Manager, Business Systems",
                "urlTitle": "Manager%2C-Business-Systems",
                "jobLocationShort": ["Toronto, ON", "Oshawa, ON"],
            },
        },
    ],
}

SEARCH_PAGE = """<html><body>
<table id="searchresults"><tbody>
<tr class="data-row">
  <td class="colTitle"><a href="/job/Toronto-Analyst-ON/12345/">Business Analyst</a></td>
  <td class="colLocation">Toronto, ON, CA</td>
  <td class="colDate">Oct 4, 2026</td>
</tr>
<tr class="data-row">
  <td class="colTitle"><a href="https://other.example/job/External/12346/">External job</a></td>
  <td class="colLocation">Toronto, ON, CA</td>
  <td class="colDate">Oct 4, 2026</td>
</tr>
</tbody></table>
</body></html>"""

DETAIL_PAGE = """<html><body>
<div class="jobdescription"><h2>Role</h2><p>Build reliable services.</p></div>
</body></html>"""

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title><![CDATA[Digital Solutions Architect (Toronto, ON, CA)]]></title>
    <description><![CDATA[<div><h2>Summary</h2><p>Design useful systems.</p></div>]]></description>
    <pubDate>Sun, 18 Oct 2026 07:00:00 GMT</pubDate>
    <link>https://jobs.example.com/Example/job/Toronto-Digital-Solutions-Architect-ON/1431751900/</link>
    <guid>https://jobs.example.com/example-job</guid>
  </item>
  <item>
    <title><![CDATA[Financial Analyst]]></title>
    <description><![CDATA[No location suffix.]]></description>
    <link>https://jobs.example.com/Example/job/Financial-Analyst/1431751901/</link>
  </item>
  <item><title>Missing link</title></item>
</channel></rss>"""


def test_feed_url_from_category_page_or_feed():
    assert successfactors.feed_url(BOARD) == FEED
    assert successfactors.feed_url(FEED) == FEED


def test_feed_url_rejects_unrecognized_urls():
    with pytest.raises(ValueError, match="category page or RSS category feed"):
        successfactors.feed_url("https://jobs.example.com/Example/search/")


def test_parse_feed_extracts_records_and_full_descriptions():
    first, second = successfactors.parse_feed(SAMPLE)

    assert first.title == "Digital Solutions Architect"
    assert first.location == "Toronto, ON, CA"
    assert first.source_job_id == "1431751900"
    assert first.url.endswith("/1431751900/")
    assert "Design useful systems." in first.description
    assert "<" not in first.description
    assert first.posted_at is not None and first.posted_at.tzinfo == timezone.utc

    assert second.title == "Financial Analyst"
    assert second.location == ""
    assert second.description == "No location suffix."
    assert second.posted_at is None


def test_parse_search_results_extracts_job_summary_fields():
    record, = successfactors.parse_search_results(SEARCH_PAGE, SEARCH)

    assert record.source_job_id == "12345"
    assert record.url == "https://jobs.example.com/job/Toronto-Analyst-ON/12345/"
    assert record.title == "Business Analyst"
    assert record.location == "Toronto, ON, CA"
    assert record.posted_at is not None
    assert record.posted_at.tzinfo == timezone.utc


def test_parse_search_results_accepts_a_tenant_prefixed_search_path():
    board = "https://jobs.example.com/Tangerine/search/?q="
    record, = successfactors.parse_search_results(SEARCH_PAGE, board)
    assert record.url == "https://jobs.example.com/job/Toronto-Analyst-ON/12345/"


def test_parse_search_results_rejects_unrecognized_html():
    with pytest.raises(ValueError, match="missing its results table"):
        successfactors.parse_search_results("<html></html>", SEARCH)


def test_build_recruiting_payload_maps_board_search_filters():
    payload = successfactors.build_recruiting_payload(OPG_SEARCH, 2, "en_GB")

    assert payload == {
        "locale": "en_GB",
        "pageNumber": 2,
        "sortBy": "",
        "keywords": "",
        "location": "",
        "facetFilters": {"jobLocationCity": ["Oshawa"]},
        "brand": "",
        "skills": [],
        "categoryId": 0,
        "alertId": "",
        "rcmCandidateId": "",
    }


def test_build_recruiting_payload_rejects_invalid_facet_filters():
    with pytest.raises(ValueError, match="facetFilters must contain valid JSON"):
        successfactors.build_recruiting_payload(
            "https://jobs.example.com/search/?facetFilters=invalid", 0, "en_GB"
        )


def test_parse_recruiting_results_builds_records_and_locale_qualified_urls():
    first, second = successfactors.parse_recruiting_results(
        RECRUITING_SAMPLE, OPG_SEARCH, "en_GB"
    )

    assert first.source_job_id == "12345"
    assert first.title == "Senior Data Analyst"
    assert first.url == "https://jobs.opg.com/job/Senior-Data-Analyst/12345-en_GB"
    assert first.location == "Oshawa, ON"
    assert first.posted_at.isoformat() == "2026-10-15T00:00:00+00:00"

    assert second.source_job_id == "12346"
    assert second.url == (
        "https://jobs.opg.com/job/Manager%2C-Business-Systems/12346-en_GB"
    )
    assert second.location == "Toronto, ON, Oshawa, ON"


def test_parse_recruiting_results_rejects_missing_job_list():
    with pytest.raises(ValueError, match="missing its job list"):
        successfactors.parse_recruiting_results({}, OPG_SEARCH, "en_GB")


def test_fetch_list_uses_and_paginates_public_recruiting_widget(monkeypatch):
    first_page = Mock()
    first_page.json.return_value = {
        "totalJobs": 2,
        "jobSearchResult": RECRUITING_SAMPLE["jobSearchResult"][:1],
    }
    second_page = Mock()
    second_page.json.return_value = {
        "totalJobs": 2,
        "jobSearchResult": RECRUITING_SAMPLE["jobSearchResult"][1:],
    }
    session = Mock()
    session.get.return_value = Mock(text=WIDGET_PAGE)
    session.post.side_effect = [first_page, second_page]
    monkeypatch.setattr(successfactors.time, "sleep", lambda _seconds: None)

    records = successfactors.fetch_list(OPG_SEARCH, session)

    assert [record.source_job_id for record in records] == ["12345", "12346"]
    assert session.get.call_args == call(OPG_SEARCH, headers=successfactors.UA, timeout=30)
    assert [request.kwargs["json"]["pageNumber"] for request in session.post.call_args_list] == [
        0,
        1,
    ]
    assert all(
        request.args[0] == "https://jobs.opg.com/services/recruiting/v1/jobs"
        for request in session.post.call_args_list
    )


def test_parse_search_detail_extracts_plain_description():
    detail = successfactors.parse_search_detail(DETAIL_PAGE)
    assert detail["description"] == "Role\nBuild reliable services."


def test_parse_search_detail_extracts_opg_joblayouttoken_sections():
    page = """<html><body><div class="job">
      <div class="joblayouttoken">Job Title: Senior Data Analyst</div>
      <div class="joblayouttoken">Posting Start Date: 15/10/2026</div>
      <div class="joblayouttoken"><h2>Job Overview</h2><p>Build reliable reports.</p></div>
      <div class="joblayouttoken"><h2>Qualifications</h2><p>Experience with SQL.</p></div>
    </div></body></html>"""

    detail = successfactors.parse_search_detail(page)

    assert "Job Overview" in detail["description"]
    assert "Build reliable reports." in detail["description"]
    assert "Qualifications" in detail["description"]
    assert "Job Title: Senior Data Analyst" not in detail["description"]


def test_parse_search_detail_rejects_missing_description():
    with pytest.raises(ValueError, match="missing its description"):
        successfactors.parse_search_detail("<html><body>No job text</body></html>")


def test_fetch_detail_rejects_a_job_url_from_another_host():
    record = JobRecord("1", "https://other.example/job/1", "External")
    with pytest.raises(ValueError, match="does not match the selected board"):
        successfactors.fetch_detail(SEARCH, record)
