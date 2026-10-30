import json
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

PAGE_SIZE = 50
MAX_JOBS = 500  # most jobs one list fetch returns (scrape warns when it is reached)
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}


def normalize_board_url(board_url):
    return board_url.split("?")[0].rstrip("/")


def build_search_payload(skip=0, top=PAGE_SIZE, query=""):
    return {
        "opportunitySearch": {
            "Top": top,
            "Skip": skip,
            "QueryString": query,
            "Filters": [
                {"t": "TermsSearchFilterDto", "fieldName": n, "extra": None, "values": []}
                for n in (4, 5, 6, 37)
            ],
        },
        "matchCriteria": {
            "PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [],
            "Skills": [], "hasNoLicenses": False, "SkippedSkills": [],
        },
    }


def _location_text(locations):
    parts = []
    for loc in locations or []:
        addr = loc.get("Address") or {}
        city = addr.get("City") or loc.get("LocalizedName") or ""
        prov = (addr.get("State") or {}).get("Code") or ""
        parts.append(", ".join(p for p in (city, prov) if p))
    return "; ".join(p for p in parts if p)


def parse_search_results(data, board_url):
    base = normalize_board_url(board_url)
    jobs = []
    for opp in data.get("opportunities", []):
        posted = opp.get("PostedDate")
        jobs.append(JobRecord(
            source_job_id=opp["Id"],
            url=f"{base}/OpportunityDetail?opportunityId={opp['Id']}",
            title=opp.get("Title", ""),
            location=_location_text(opp.get("Locations")),
            work_mode=str(opp.get("JobLocationType") or ""),  # raw; map later
            employment_type="Full-time" if opp.get("FullTime") else "Not full-time",
            posted_at=datetime.fromisoformat(posted.replace("Z", "+00:00")) if posted else None,
            description=opp.get("BriefDescription") or "",
        ))
    return jobs


def parse_detail_html(html):
    marker = "CandidateOpportunityDetail("
    i = html.find(marker)
    if i == -1:
        return ""
    obj, _ = json.JSONDecoder().raw_decode(html, i + len(marker))
    return BeautifulSoup(obj.get("Description") or "", "html.parser").get_text("\n", strip=True)


def fetch_list(board_url, session=None, max_jobs=MAX_JOBS, options=None):
    session = session or requests.Session()
    url = normalize_board_url(board_url) + "/JobBoardView/LoadSearchResults"
    jobs, skip = [], 0
    while True:
        r = session.post(url, json=build_search_payload(skip), headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
        page = parse_search_results(data, board_url)
        jobs.extend(page)
        skip += PAGE_SIZE
        if not page or skip >= data.get("totalCount", 0) or len(jobs) >= max_jobs:
            return jobs
        time.sleep(1)


def fetch_description(job_url, session=None):
    session = session or requests.Session()
    r = session.get(job_url, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_detail_html(r.text)


def fetch_detail(board_url, rec, session=None, options=None):
    return {"description": fetch_description(rec.url, session)}