import pytest

from scrapers import jazzhr

BOARD = "https://example.applytojob.com/apply"

LISTING = """<html><body>
<div class="jobs-list">
  <ul class="list-group">
    <li class="list-group-item">
      <h3 class="list-group-item-heading">
        <a href="/apply/job-123/Business-Analyst">Business Analyst</a>
      </h3>
      <ul class="list-inline list-group-item-text">
        <li><i class="fa fa-map-marker"></i>Toronto, ON, Canada</li>
        <li><i class="fa fa-sitemap"></i>Business Operations</li>
      </ul>
    </li>
    <li class="list-group-item">
      <h3 class="list-group-item-heading">
        <a href="https://other.applytojob.com/apply/job-456/Other">Other board</a>
      </h3>
    </li>
  </ul>
</div>
</body></html>"""

DETAIL = """<html><body>
  <div id="job-description">
    <p>Help customers.</p>
    <ul><li>Work with the team.</li><li>Document decisions.</li></ul>
  </div>
</body></html>"""


def test_parse_board_url_accepts_applytojob_account():
    assert jazzhr.parse_board_url(BOARD) == {
        "hostname": "example.applytojob.com",
        "list_url": BOARD,
    }


def test_parse_board_url_rejects_other_hosts():
    with pytest.raises(ValueError, match="Expected a JazzHR"):
        jazzhr.parse_board_url("https://example.com/apply")


def test_parse_job_list_extracts_title_location_and_id():
    records = jazzhr.parse_job_list(LISTING, BOARD)

    assert len(records) == 1
    assert records[0].source_job_id == "job-123"
    assert records[0].url == "https://example.applytojob.com/apply/job-123/Business-Analyst"
    assert records[0].title == "Business Analyst"
    assert records[0].location == "Toronto, ON, Canada"


def test_parse_job_list_rejects_unrecognized_layout():
    with pytest.raises(ValueError, match="missing the expected jobs list"):
        jazzhr.parse_job_list("<html><body>No openings</body></html>", BOARD)


def test_parse_job_detail_extracts_plain_text():
    detail = jazzhr.parse_job_detail(DETAIL)
    assert detail["description"] == "Help customers.\nWork with the team.\nDocument decisions."


def test_parse_job_detail_rejects_missing_or_empty_description():
    with pytest.raises(ValueError, match="missing its job description"):
        jazzhr.parse_job_detail("<html><body>No description</body></html>")
    with pytest.raises(ValueError, match="empty job description"):
        jazzhr.parse_job_detail('<div id="job-description">  </div>')
