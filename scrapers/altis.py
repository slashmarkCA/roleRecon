import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

API_BASE = "https://apis.altisexcel.com/Applicant"
PORTAL_BASE = "https://jobportal.altis.com"
SEARCH_PATH = "/jobs/ads/Search"
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}


def parse_board_url(board_url):
    """Validate Altis' public job portal URL."""
    parsed = urlparse(board_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc.lower() != "jobportal.altis.com"
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Expected the Altis job portal URL https://jobportal.altis.com/")
    return {
        "search_url": f"{API_BASE}{SEARCH_PATH}",
        "locations": parse_qs(parsed.query).get("location", []),
    }


def build_search_payload(locations=None):
    """Build the public portal's job-search request, optionally filtered by location."""
    return {
        "keyword": None,
        "remoteWorkOptionId": None,
        "jobTypeIds": [],
        "industryIds": [],
        "specializations": [],
        "locations": list(locations or []),
        "businessType": "",
    }


def _parse_date(value):
    if not isinstance(value, str) or not value:
        return None
    for date_format in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _salary_text(data):
    start = str(data.get("salaryFrom") or "").strip()
    end = str(data.get("salaryTo") or "").strip()
    unit = str(data.get("salaryPer") or "").strip()
    if start and end and start != end:
        amount = f"{start}-{end}"
    else:
        amount = start or end
    return " ".join(part for part in (amount, unit) if part)


def _html_to_text(value):
    soup = BeautifulSoup(value or "", "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _record_from_job(job):
    if not isinstance(job, dict):
        raise ValueError("Altis job search response contains an invalid entry")
    job_id = str(job.get("jobId") or "").strip()
    title = str(job.get("jobTitle") or "").strip()
    if not job_id or not title:
        raise ValueError("Altis job is missing its id or title")
    if not job_id.isdigit():
        raise ValueError("Altis job id is not numeric")

    return JobRecord(
        source_job_id=job_id,
        url=f"{PORTAL_BASE}/jobs/{job_id}",
        title=title,
        location=str(job.get("location") or "").strip(),
        work_mode=str(job.get("availabilityTypeId") or "").strip(),
        employment_type=str(job.get("jobType") or "").strip(),
        salary_text=_salary_text(job),
        posted_at=_parse_date(job.get("datePosted")),
    )


def parse_job_list(data, board_url):
    """Parse the Altis public search API's list of job summaries."""
    parse_board_url(board_url)
    if not isinstance(data, list):
        raise ValueError("Altis job search response is not a list")
    return [_record_from_job(job) for job in data]


def parse_job_detail(data):
    """Parse a job returned by Altis' public job-detail endpoint."""
    if not isinstance(data, dict):
        raise ValueError("Altis job detail response is not an object")
    description = _html_to_text(data.get("jobDescription"))
    if not description:
        raise ValueError("Altis job detail is missing its description")
    record = _record_from_job(data)
    return {
        "description": description,
        "location": record.location,
        "work_mode": record.work_mode,
        "employment_type": record.employment_type,
        "salary_text": record.salary_text,
        "posted_at": record.posted_at,
        "title": record.title,
    }


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    response = session.post(
        board["search_url"],
        json=build_search_payload(board["locations"]),
        headers={**UA, "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_list(response.json(), board_url)


def fetch_detail(board_url, rec, session=None):
    parse_board_url(board_url)
    parsed_url = urlparse(rec.url)
    match = re.fullmatch(r"/jobs/(\d+)(?:/[^/]*)?/?", parsed_url.path)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc.lower() != "jobportal.altis.com"
        or match is None
        or match.group(1) != rec.source_job_id
    ):
        raise ValueError("Altis job URL does not match the requested posting")

    session = session or requests.Session()
    response = session.get(
        f"{API_BASE}/jobs/ads/{rec.source_job_id}",
        headers={**UA, "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_detail(response.json())
