from scrapers import erecruit

BOARD = "https://careers.example.org/erecruit/Search_Results.aspx?AdvancedSearch=Y"

# Mimics the real feed's shape: empty nested <item> tags, a closed <rss>, then the postings as
# plain markup inside an HTML block.
SAMPLE = """<?xml version="1.0" encoding="Windows-1252"?>
<rss version="2.0"><channel><item><item><item></item></item></item></channel></rss>
<main><div id="pnlRSS">
<title>Example Careers</title><description>RSS Description </description><link>https://careers.example.org </link><ttl>60 </ttl>
<h1>Dietary Aide      </h1><description><br><p><b>UNION</b><br><i>Job Title:</i> Dietary Aide<br><i>Status:</i> Part Time<br><i>Location:</i> Springfield Hospital, Shelbyville<br><i>Wage Schedule:</i> $20.00 - $25.00 per hour<br><br>Details here.</p></description><link>https://careers.example.org/VacancyDetail.aspx?VacancyUID=000000000001 </link><pubDate>Thu, 08 Oct 2026 13:25:08 GMT </pubDate>
<h1>Systems Analyst</h1><description>No labelled fields here.</description><link>https://careers.example.org/VacancyDetail.aspx?VacancyUID=000000000002 </link><pubDate>Fri, 09 Oct 2026 09:00:00 GMT </pubDate>
</div></main>"""


def test_feed_url_from_any_erecruit_page():
    assert erecruit.feed_url(BOARD) == "https://careers.example.org/erecruit/RSS.aspx"
    assert erecruit.feed_url("https://careers.example.org/erecruit/RSS.aspx") == \
        "https://careers.example.org/erecruit/RSS.aspx"


def test_parse_feed_reads_postings_from_the_malformed_feed():
    first, second = erecruit.parse_feed(SAMPLE, BOARD)
    assert first.title == "Dietary Aide"
    assert first.source_job_id == "000000000001"
    assert first.url == "https://careers.example.org/VacancyDetail.aspx?VacancyUID=000000000001"
    assert first.location == "Springfield Hospital, Shelbyville"
    assert first.employment_type == "Part Time"
    assert first.salary_text == "$20.00 - $25.00 per hour"
    assert first.posted_at is not None and first.posted_at.tzinfo is not None
    assert "Details here." in first.description and "<" not in first.description


def test_posting_without_labelled_fields_gets_empty_ones():
    _, second = erecruit.parse_feed(SAMPLE, BOARD)
    assert second.title == "Systems Analyst"
    assert second.location == "" and second.employment_type == "" and second.salary_text == ""
    assert second.description == "No labelled fields here."


def test_feed_bytes_are_decoded_as_utf8_or_windows_1252():
    text = SAMPLE.replace("Dietary Aide      ", "Nurse\u2019s Aide")
    for encoded in (text.encode("utf-8"), text.encode("cp1252")):
        jobs = erecruit.parse_feed(encoded, BOARD)
        assert jobs[0].title == "Nurse\u2019s Aide"
