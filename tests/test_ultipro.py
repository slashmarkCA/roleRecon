import json

from scrapers import ultipro

BOARD = "https://recruiting.ultipro.ca/ACME5000ACME/JobBoard/00000000-0000-0000-0000-000000000000"

SEARCH = {
    "totalCount": 2,
    "opportunities": [
        {
            "Id": "11111111-aaaa-bbbb-cccc-000000000001",
            "Title": "QA Analyst",
            "FullTime": True,
            "PostedDate": "2026-01-02T03:04:05.000Z",
            "BriefDescription": "Short summary.",
            "Locations": [{"Address": {"City": "Toronto", "State": {"Code": "ON"}}}],
        },
        {
            "Id": "11111111-aaaa-bbbb-cccc-000000000002",
            "Title": "Business Analyst",
            "FullTime": False,
            "Locations": [{"LocalizedName": "Head Office"}],
        },
    ],
}


def test_board_url_is_normalized():
    assert ultipro.normalize_board_url(BOARD + "/?q=analyst") == BOARD


def test_search_payload_pages_with_skip():
    payload = ultipro.build_search_payload(skip=50)
    assert payload["opportunitySearch"]["Skip"] == 50
    assert payload["opportunitySearch"]["Top"] == ultipro.PAGE_SIZE


def test_parse_search_results():
    first, second = ultipro.parse_search_results(SEARCH, BOARD)
    assert first.title == "QA Analyst"
    assert first.location == "Toronto, ON"
    assert first.employment_type == "Full-time"
    assert first.posted_at is not None
    assert first.url == f"{BOARD}/OpportunityDetail?opportunityId={first.source_job_id}"
    assert second.location == "Head Office"  # falls back to the localized name
    assert second.employment_type == "Not full-time"
    assert second.posted_at is None


def test_parse_detail_html_reads_the_embedded_json():
    embedded = json.dumps({"Description": "<p>Hello <b>world</b></p>"})
    html = f"<script>var o = new CandidateOpportunityDetail({embedded});</script>"
    text = ultipro.parse_detail_html(html)
    assert "Hello" in text and "world" in text and "<" not in text


def test_parse_detail_html_without_the_marker_is_empty():
    assert ultipro.parse_detail_html("<html>nothing here</html>") == ""
