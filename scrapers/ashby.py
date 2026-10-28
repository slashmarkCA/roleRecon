import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
API = "https://api.ashbyhq.com/posting-api/job-board"


def parse_board_slug(board_url):
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname != "jobs.ashbyhq.com" or not parts:
        raise ValueError("Expected an Ashby board URL like jobs.ashbyhq.com/<board>")
    return parts[0]


def _html_to_text(value):
    soup = BeautifulSoup(value or "", "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _parse_date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _employment_type(value):
    normalized = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value or "").strip()
    return {
        "full time": "Full-time",
        "part time": "Part-time",
    }.get(normalized.lower(), normalized)


def parse_jobs(data, board_url):
    slug = parse_board_slug(board_url)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("Ashby response is missing its jobs list")

    records = []
    for job in data["jobs"]:
        if not isinstance(job, dict):
            raise ValueError("Ashby jobs list contains an invalid entry")
        if job.get("isListed") is False:
            continue

        job_id = str(job.get("id") or "").strip()
        title = str(job.get("title") or "").strip()
        if not job_id or not title:
            raise ValueError("Ashby job is missing its id or title")

        url = job.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{job_id}"
        parsed_url = urlparse(url)
        if (
            parsed_url.hostname != "jobs.ashbyhq.com"
            or not parsed_url.path.startswith(f"/{slug}/")
        ):
            raise ValueError("Ashby job URL does not match the board")

        workplace = str(job.get("workplaceType") or "").strip()
        if not workplace and job.get("isRemote"):
            workplace = "Remote"

        records.append(JobRecord(
            source_job_id=job_id,
            url=url,
            title=title,
            location=str(job.get("location") or "").strip(),
            work_mode=workplace,
            employment_type=_employment_type(str(job.get("employmentType") or "")),
            posted_at=_parse_date(job.get("publishedAt")),
            description=_html_to_text(job.get("descriptionHtml")),
        ))
    return records


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    slug = parse_board_slug(board_url)
    response = session.get(f"{API}/{slug}", headers=UA, timeout=30)
    response.raise_for_status()
    return parse_jobs(response.json(), board_url)


def fetch_detail(board_url, rec, session=None):
    return {}
