import pytest

from scrapers import avature
from scrapers.base import JobRecord

BOARD = (
    "https://jobs.example.com/en_US/externaljobs/SearchJobs/"
    "?country=Canada&folderRecordsPerPage=6"
)

SEARCH_PAGE = """<html><body>
<div class="results results--listed">
  <article class="article article--result 1" id="article--1">
    <h3><a href="/en_US/externaljobs/JobDetail/527353">Service Specialist</a></h3>
    <div class="article__header__text__subtitle">
      <span class="list-item-location">
        <span class="list-item-jobCity">Ottawa</span>,
        <span class="list-item-jobState">Ontario</span>,
        <span class="list-item-jobCountry">Canada</span>
      </span>
      <span class="list-item-jobId">Job ID: 527353</span>
    </div>
  </article>
  <article class="article article--result 2">
    <h3><a href="/en_US/externaljobs/JobDetail/527133">Sprinkler Fitter</a></h3>
  </article>
</div>
<a href="?country=Canada&amp;folderRecordsPerPage=6&amp;folderOffset=6">Next &gt;&gt;</a>
</body></html>"""

DETAIL_PAGE = """<html><body>
<article class="article article--details">
  <div class="article__content">
    <div class="article__content__view">
      <div class="article__content__view__field__value">
        <p>Install and maintain building automation systems.</p>
      </div>
      <div class="article__content__view__field__value">
        <p>Siemens is an equal opportunity employer.</p>
      </div>
    </div>
  </div>
</article>
</body></html>"""


def test_parse_board_url_accepts_searchjobs_and_rejects_other_urls():
    parsed = avature.parse_board_url(BOARD)
    assert parsed["host"] == "jobs.example.com"
    assert parsed["search_url"] == BOARD
    with pytest.raises(ValueError, match="Expected an Avature SearchJobs"):
        avature.parse_board_url("https://jobs.example.com/en_US/externaljobs/JobDetail/123")


def test_parse_search_results_extracts_job_cards():
    first, second = avature.parse_search_results(SEARCH_PAGE, BOARD)

    assert first.source_job_id == "527353"
    assert first.url == "https://jobs.example.com/en_US/externaljobs/JobDetail/527353"
    assert first.title == "Service Specialist"
    assert first.location == "Ottawa, Ontario, Canada"
    assert second.source_job_id == "527133"
    assert second.location == ""


def test_parse_search_results_rejects_missing_result_container():
    with pytest.raises(ValueError, match="missing its results"):
        avature.parse_search_results("<html></html>", BOARD)


def test_next_page_url_preserves_avature_filters_and_offset():
    current = "https://jobs.example.com/en_US/externaljobs/SearchJobs/?country=Canada"
    assert avature.next_page_url(SEARCH_PAGE, current) == (
        "https://jobs.example.com/en_US/externaljobs/SearchJobs/"
        "?country=Canada&folderRecordsPerPage=6&folderOffset=6"
    )
    assert avature.next_page_url("<html></html>", current) is None


def test_parse_job_detail_extracts_posting_description():
    assert avature.parse_job_detail(DETAIL_PAGE) == {
        "description": "Install and maintain building automation systems."
    }


def test_parse_job_detail_rejects_missing_description():
    with pytest.raises(ValueError, match="missing its description"):
        avature.parse_job_detail("<html><body>No description</body></html>")


def test_fetch_detail_rejects_job_url_from_another_host():
    record = JobRecord("527353", "https://other.example/JobDetail/527353", "Service Specialist")
    with pytest.raises(ValueError, match="does not match the selected portal"):
        avature.fetch_detail(BOARD, record)
