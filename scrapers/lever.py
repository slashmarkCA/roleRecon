from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
API = "https://api.lever.co/v0/postings"


def parse_board_url(board_url):
    """Return a Lever site name and its public postings API URL."""
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "jobs.lever.co" or not parts:
        raise ValueError("Expected a Lever board URL like jobs.lever.co/<site>")
    site = parts[0]
    return {
        "site": site,
        "board_url": f"https://jobs.lever.co/{site}",
        "list_url": f"{API}/{site}",
    }


def _html_to_text(raw):
    return BeautifulSoup(raw or "", "html.parser").get_text("\n", strip=True)


def _parse_posted_at(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _work_mode(value):
    normalized = (value or "").strip().lower().replace("_", "-")
    if normalized in {"on-site", "onsite"}:
        return "On-site"
    if normalized in {"remote", "hybrid"}:
        return normalized.title()
    return normalized.title()


def _description(posting):
    sections = []
    description = posting.get("descriptionPlain") or _html_to_text(posting.get("description"))
    if description:
        sections.append(description.strip())

    for item in posting.get("lists") or []:
        heading = (item.get("text") or "").strip()
        content = _html_to_text(item.get("content"))
        if content:
            sections.append("\n".join(part for part in (heading, content) if part))

    additional = posting.get("additionalPlain") or _html_to_text(posting.get("additional"))
    if additional:
        sections.append(additional.strip())
    return "\n\n".join(sections)


def parse_jobs(data, board_url):
    board = parse_board_url(board_url)
    if not isinstance(data, list):
        raise ValueError("Lever response must be a list of postings")

    records = []
    for posting in data:
        job_id = posting.get("id")
        if job_id is None:
            continue
        categories = posting.get("categories") or {}
        location = categories.get("location") or ""
        if not location and categories.get("allLocations"):
            location = ", ".join(categories["allLocations"])
        url = posting.get("hostedUrl") or f"{board['board_url']}/{job_id}"
        records.append(JobRecord(
            source_job_id=str(job_id),
            url=url,
            title=posting.get("text") or "",
            location=location,
            work_mode=_work_mode(posting.get("workplaceType")),
            employment_type=categories.get("commitment") or "",
            posted_at=_parse_posted_at(posting.get("createdAt")),
            description=_description(posting),
        ))
    return records


def fetch_list(board_url, session=None, options=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    response = session.get(
        board["list_url"],
        params={"mode": "json"},
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_jobs(response.json(), board_url)


def fetch_detail(board_url, rec, session=None, options=None):
    return {}
