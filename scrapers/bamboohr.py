import html
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)", "Accept": "application/json"}


def _base(board_url):
    return f"https://{urlparse(board_url).netloc}"


def _html_to_text(raw):
    return BeautifulSoup(html.unescape(raw or ""), "html.parser").get_text("\n", strip=True)


def _place(loc):
    loc = loc or {}
    return ", ".join(p for p in (loc.get("city"), loc.get("state") or loc.get("province")) if p)


def parse_list(data, board_url):
    base = _base(board_url)
    jobs = []
    for r in data.get("result", []):
        job_id = str(r["id"])
        jobs.append(JobRecord(
            source_job_id=job_id,
            url=f"{base}/careers/{job_id}",
            title=r.get("jobOpeningName", ""),
            location=_place(r.get("location")) or _place(r.get("atsLocation")),
            work_mode="Remote" if r.get("isRemote") else "",
            employment_type=r.get("employmentStatusLabel") or "",
        ))
    return jobs


def parse_detail(data):
    opening = (data.get("result") or {}).get("jobOpening") or {}
    posted = None
    if opening.get("datePosted"):
        try:
            posted = datetime.fromisoformat(opening["datePosted"]).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return {
        "description": _html_to_text(opening.get("description")),
        "location": _place(opening.get("location")),
        "posted_at": posted,
    }


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    r = session.get(f"{_base(board_url)}/careers/list", headers=UA, timeout=30)
    r.raise_for_status()
    return parse_list(r.json(), board_url)


def fetch_detail(board_url, rec, session=None):
    session = session or requests.Session()
    r = session.get(f"{_base(board_url)}/careers/{rec.source_job_id}/detail", headers=UA, timeout=30)
    r.raise_for_status()
    return parse_detail(r.json())
