import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord
from .workable import parse_job_detail

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
CANADA_CARD_COUNT = re.compile(r"^\d+$")
WORKABLE_JOB_PATH = re.compile(r"^/j/([A-Za-z0-9]+)/?$")


def parse_board_url(board_url):
    """Validate Tiger Analytics' public current-openings page."""
    parsed = urlparse(board_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc.lower() not in {"tigeranalytics.com", "www.tigeranalytics.com"}
        or parsed.path.rstrip("/") != "/about-us/current-openings"
    ):
        raise ValueError("Expected Tiger Analytics' current-openings page")
    return board_url


def parse_job_list(page_html, board_url):
    """Parse the Canadian job cards embedded in Tiger Analytics' careers page."""
    parse_board_url(board_url)
    soup = BeautifulSoup(page_html, "html.parser")
    pagers = soup.select('.career_pagination[data-jc="CA"]')
    if len(pagers) != 1:
        raise ValueError("Tiger Analytics page is missing its Canada results")

    results = pagers[0].find_parent(class_="results")
    if results is None:
        raise ValueError("Tiger Analytics Canada results are missing their job cards")

    records = []
    for row in results.select(".all-jobs-list-wrap"):
        title_node = row.select_one(".jobs-title")
        apply_link = row.select_one(".jobs-apply a[href]")
        if title_node is None or apply_link is None:
            continue

        apply_url = urlparse(apply_link["href"])
        match = WORKABLE_JOB_PATH.fullmatch(apply_url.path)
        if apply_url.netloc.lower() != "apply.workable.com" or match is None:
            continue

        job_id = match.group(1)
        location_node = row.select_one(".jobs-location")
        location = location_node.get_text(" ", strip=True) if location_node else ""
        if location.upper() == "CA":
            location = "Canada"
        records.append(JobRecord(
            source_job_id=job_id,
            url=f"https://apply.workable.com/j/{job_id}",
            title=title_node.get_text(" ", strip=True),
            location=location,
        ))

    declared_total = pagers[0].get("data-tj", "")
    if not CANADA_CARD_COUNT.fullmatch(declared_total):
        raise ValueError("Tiger Analytics Canada results are missing their job count")
    if len(records) != int(declared_total):
        raise ValueError(
            f"Tiger Analytics Canada results declared {declared_total} jobs "
            f"but contained {len(records)} valid job cards"
        )
    return records


def parse_detail(markdown):
    """Parse a Workable Markdown job detail using the shared Workable parser."""
    return parse_job_detail(markdown)


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    response = session.get(parse_board_url(board_url), headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_list(response.text, board_url)


def fetch_detail(board_url, rec, session=None):
    parse_board_url(board_url)
    parsed_url = urlparse(rec.url)
    match = WORKABLE_JOB_PATH.fullmatch(parsed_url.path)
    if parsed_url.netloc.lower() != "apply.workable.com" or match is None:
        raise ValueError("Workable job URL does not match the Tiger Analytics board")

    detail_url = (
        f"https://apply.workable.com/tiger-analytics/jobs/view/{match.group(1)}.md"
    )
    session = session or requests.Session()
    response = session.get(
        detail_url,
        headers={**UA, "Accept": "text/markdown, text/plain"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_detail(response.text)
