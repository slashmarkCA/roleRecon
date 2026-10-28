from datetime import timezone

import pytest

from scrapers.base import JobRecord
from scrapers import successfactors

BOARD = "https://jobs.example.com/Example/go/Category-Page-Example/123456/"
FEED = "https://jobs.example.com/services/rss/category/?catid=123456"
SEARCH = "https://jobs.example.com/search/?q=&locationsearch=ontario"

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


def test_parse_search_results_rejects_unrecognized_html():
    with pytest.raises(ValueError, match="missing its results table"):
        successfactors.parse_search_results("<html></html>", SEARCH)


def test_parse_search_detail_extracts_plain_description():
    detail = successfactors.parse_search_detail(DETAIL_PAGE)
    assert detail["description"] == "Role\nBuild reliable services."


def test_parse_search_detail_rejects_missing_description():
    with pytest.raises(ValueError, match="missing its description"):
        successfactors.parse_search_detail("<html><body>No job text</body></html>")


def test_fetch_detail_rejects_a_job_url_from_another_host():
    record = JobRecord("1", "https://other.example/job/1", "External")
    with pytest.raises(ValueError, match="does not match the selected board"):
        successfactors.fetch_detail(SEARCH, record)
