import re
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

API_BASE = "https://gateway.risepeople.com/applicant_tracking/public"
CAREERS_URL = f"{API_BASE}/careers"
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
COMPANY_URI = re.compile(r"^[a-z0-9-]+$")
LANGUAGE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)


def parse_board_url(board_url):
    """Extract the company and language from a Rise People careers URL."""
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname != "careers.risepeople.com"
        or len(parts) < 2
        or not COMPANY_URI.fullmatch(parts[0])
        or not LANGUAGE.fullmatch(parts[1])
    ):
        raise ValueError("Expected a Rise People careers board or posting URL")

    return {"company_uri": parts[0], "language": parts[1]}


def _location(position):
    city = str(position.get("city") or "").strip()
    province = str(position.get("province") or "").strip()
    country = str(position.get("country") or "").strip()
    location = ", ".join(part for part in (city, province or country) if part)

    if position.get("remote_position"):
        return f"{location} or Remote" if location else "Remote"
    return location


def _employment_type(position):
    job_type = position.get("job_type") or []
    if isinstance(job_type, str):
        return job_type.strip()
    if isinstance(job_type, list):
        return ", ".join(str(item).strip() for item in job_type if str(item).strip())
    return ""


def _job_url(board_url, source_job_id, title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return f"{board_url.rstrip('/')}/{source_job_id}_{slug}"


def parse_job_list(data, board_url):
    """Parse the public careers API response into job summaries."""
    board = parse_board_url(board_url)
    if not isinstance(data, dict) or not isinstance(data.get("departments"), list):
        raise ValueError("Rise People careers response is missing its departments")

    careers_url = (
        f"https://careers.risepeople.com/"
        f"{board['company_uri']}/{board['language']}"
    )
    records = []
    for department in data["departments"]:
        if not isinstance(department, dict) or not isinstance(department.get("positions"), list):
            raise ValueError("Rise People careers response has an invalid department")
        for position in department["positions"]:
            if not isinstance(position, dict) or position.get("id") is None or not position.get("title"):
                raise ValueError("Rise People careers response has an invalid position")
            source_job_id = str(position["id"])
            if not source_job_id.isdigit():
                raise ValueError("Rise People position has an invalid id")
            records.append(JobRecord(
                source_job_id=source_job_id,
                url=_job_url(careers_url, source_job_id, str(position["title"])),
                title=str(position["title"]).strip(),
                location=_location(position),
                work_mode="Remote" if position.get("remote_position") else "",
                employment_type=_employment_type(position),
            ))
    return records


def _posted_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None


def parse_job_detail(data, board_url):
    """Parse one public Rise People position response."""
    board = parse_board_url(board_url)
    if not isinstance(data, dict) or not isinstance(data.get("descriptions"), list):
        raise ValueError("Rise People position response is missing its descriptions")

    descriptions = data["descriptions"]
    description = next(
        (
            item for item in descriptions
            if isinstance(item, dict)
            and str(item.get("language", "")).lower() == board["language"].lower()
        ),
        descriptions[0] if len(descriptions) == 1 and isinstance(descriptions[0], dict) else None,
    )
    if description is None:
        raise ValueError("Rise People position has no description for the requested language")

    text = BeautifulSoup(
        str(description.get("description") or ""), "html.parser"
    ).get_text("\n", strip=True)
    if not text:
        raise ValueError("Rise People position has an empty description")

    detail = {
        "description": text,
        "location": _location(description),
        "employment_type": _employment_type(description),
        "posted_at": _posted_at(data.get("opened")),
    }
    if description.get("remote_position"):
        detail["work_mode"] = "Remote"
    return detail


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    response = session.get(
        CAREERS_URL,
        params=board,
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_list(response.json(), board_url)


def fetch_detail(board_url, rec, session=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    if not str(rec.source_job_id).isdigit():
        raise ValueError("Rise People position has an invalid id")
    response = session.get(
        f"{API_BASE}/positions/{rec.source_job_id}",
        params=board,
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_detail(response.json(), board_url)
