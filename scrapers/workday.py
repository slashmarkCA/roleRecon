import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

PAGE_SIZE = 20
MAX_JOBS = 500  # most jobs one list fetch returns (scrape warns when it is reached)
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}


def parse_board_url(board_url):
    """Split a Workday board URL such as
    https://example.wd3.myworkdayjobs.com/en-US/Careers into its parts."""
    u = urlparse(board_url)
    segments = [s for s in u.path.split("/") if s]
    locale = "en-US"
    if segments and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segments[0]):
        locale = segments.pop(0)
    site = segments[0]  # ignores anything after it, e.g. /details/... or /job/...
    tenant = u.netloc.split(".")[0]
    query_params = parse_qs(u.query)
    search_text = (
        query_params.pop("searchText", None) or query_params.pop("q", [""])
    )[0]
    return {
        "host": u.netloc,
        "tenant": tenant,
        "site": site,
        "locale": locale,
        "api_base": f"https://{u.netloc}/wday/cxs/{tenant}/{site}",
        "applied_facets": query_params,
        "search_text": search_text,
    }


def build_search_payload(offset=0, limit=PAGE_SIZE, query="", applied_facets=None):
    return {
        "appliedFacets": applied_facets or {},
        "limit": limit,
        "offset": offset,
        "searchText": query,
    }


def parse_search_results(data, board_url):
    b = parse_board_url(board_url)
    jobs = []
    for p in data.get("jobPostings", []):
        path = p.get("externalPath")
        if not path:
            continue
        jobs.append(JobRecord(
            source_job_id=path,
            url=f"https://{b['host']}/{b['locale']}/{b['site']}{path}",
            title=p.get("title", ""),
            location=p.get("locationsText", "") or "",
        ))
    return jobs


def _html_to_text(html):
    return BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)


def parse_detail(data):
    """Turn a Workday job-detail JSON response into the fields we store."""
    info = data.get("jobPostingInfo", {}) or {}
    places = [info.get("location")] + list(info.get("additionalLocations") or [])
    posted = None
    start = info.get("startDate")
    if start:
        try:
            posted = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return {
        "description": _html_to_text(info.get("jobDescription")),
        "location": "; ".join(p for p in places if p),
        "work_mode": info.get("remoteType") or "",
        "employment_type": info.get("timeType") or "",
        "posted_at": posted,
    }


def fetch_list(board_url, session=None, max_jobs=MAX_JOBS):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    url = board["api_base"] + "/jobs"
    jobs, offset, total = [], 0, None
    while True:
        payload = build_search_payload(
            offset,
            query=board["search_text"],
            applied_facets=board["applied_facets"],
        )
        r = session.post(url, json=payload, headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
        if total is None:  # Workday reports the total on the first page only
            total = data.get("total", 0)
        page = parse_search_results(data, board_url)
        jobs.extend(page)
        offset += PAGE_SIZE
        if not data.get("jobPostings") or offset >= total or len(jobs) >= max_jobs:
            return jobs
        time.sleep(1)


def fetch_detail(board_url, rec, session=None):
    session = session or requests.Session()
    url = parse_board_url(board_url)["api_base"] + rec.source_job_id
    r = session.get(url, headers={**UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return parse_detail(r.json())
