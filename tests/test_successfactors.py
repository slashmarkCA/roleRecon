from datetime import timezone

from scrapers import successfactors

BOARD = "https://jobs.example.com/Example/go/Category-Page-Example/123456/"
FEED = "https://jobs.example.com/services/rss/category/?catid=123456"

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
    try:
        successfactors.feed_url("https://jobs.example.com/Example/search/")
    except ValueError as exc:
        assert "category page or RSS category feed" in str(exc)
    else:
        raise AssertionError("Expected an unrecognized URL to be rejected")


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
