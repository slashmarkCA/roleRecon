from scrapers import greenhouse

BOARD = "https://job-boards.greenhouse.io/exampleco"

DATA = {
    "jobs": [
        {
            "id": 123,
            "title": "QA Analyst",
            "absolute_url": "https://job-boards.greenhouse.io/exampleco/jobs/123",
            "location": {"name": "Toronto, ON"},
            "first_published": "2026-01-02T03:04:05-05:00",
            # Greenhouse returns the description as HTML-escaped text
            "content": "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;",
        },
        {"id": 124, "title": "Analyst without a URL or content"},
    ]
}


def test_parse_board_token():
    assert greenhouse.parse_board_token("https://job-boards.greenhouse.io/exampleco") == "exampleco"
    assert greenhouse.parse_board_token("https://boards.greenhouse.io/acme/jobs/123") == "acme"
    assert greenhouse.parse_board_token("https://example.com/careers?for=acme") == "acme"


def test_parse_jobs_decodes_the_escaped_description():
    first, second = greenhouse.parse_jobs(DATA, BOARD)
    assert first.source_job_id == "123" and first.title == "QA Analyst"
    assert first.location == "Toronto, ON"
    assert first.posted_at is not None
    assert first.description == "Hello & welcome"
    assert "&lt;" not in first.description


def test_parse_jobs_builds_a_url_when_the_feed_has_none():
    _, second = greenhouse.parse_jobs(DATA, BOARD)
    assert second.url == "https://job-boards.greenhouse.io/exampleco/jobs/124"
    assert second.description == "" and second.location == ""
