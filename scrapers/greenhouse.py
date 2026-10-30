import html
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
API = "https://boards-api.greenhouse.io/v1/boards"


def parse_board_token(board_url):
    """The board token is the first path segment of boards.greenhouse.io/<token> or
    job-boards.greenhouse.io/<token>, or the ?for=<token> value on embedded boards."""
    u = urlparse(board_url)
    qs = parse_qs(u.query)
    if "for" in qs:
        return qs["for"][0]
    segments = [s for s in u.path.split("/") if s]
    return segments[0]


def _html_to_text(raw):
    # Greenhouse returns the description as HTML-escaped text, so unescape first.
    return BeautifulSoup(html.unescape(raw or ""), "html.parser").get_text("\n", strip=True)


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_jobs(data, board_url):
    token = parse_board_token(board_url)
    jobs = []
    for j in data.get("jobs", []):
        job_id = str(j["id"])
        jobs.append(JobRecord(
            source_job_id=job_id,
            url=j.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{job_id}",
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name") or "",
            posted_at=_parse_dt(j.get("first_published") or j.get("updated_at")),
            description=_html_to_text(j.get("content")),
        ))
    return jobs


def fetch_list(board_url, session=None, options=None):
    """One request returns every job with its full description (content=true)."""
    session = session or requests.Session()
    url = f"{API}/{parse_board_token(board_url)}/jobs"
    r = session.get(url, params={"content": "true"}, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_jobs(r.json(), board_url)


def fetch_detail(board_url, rec, session=None, options=None):
    return {}  # the list response already includes the description
