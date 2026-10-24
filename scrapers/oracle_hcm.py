import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

PAGE_SIZE = 50
MAX_JOBS = 500  # most jobs one list fetch returns (scrape warns when it is reached)
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}


def parse_board_url(board_url):
    """Split an Oracle Recruiting Cloud candidate-experience URL such as
    https://ehtc.fa.ca2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?... """
    u = urlparse(board_url)
    m = re.search(r"/sites/([^/]+)", u.path)
    site = m.group(1) if m else "CX_1"
    return {
        "host": u.netloc,
        "site": site,
        "api_base": f"https://{u.netloc}/hcmRestApi/resources/latest",
    }


def _list_url(board_url, offset=0, limit=PAGE_SIZE):
    b = parse_board_url(board_url)
    return (f"{b['api_base']}/recruitingCEJobRequisitions?onlyData=true"
            f"&expand=requisitionList.secondaryLocations"
            f"&finder=findReqs;siteNumber={b['site']},limit={limit},offset={offset},"
            f"sortBy=POSTING_DATES_DESC")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if "T" not in value \
            else datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_list(data, board_url):
    """Returns (records, total_jobs) from one page of the list endpoint."""
    b = parse_board_url(board_url)
    item = (data.get("items") or [{}])[0]
    jobs = []
    for r in item.get("requisitionList", []):
        job_id = str(r["Id"])
        jobs.append(JobRecord(
            source_job_id=job_id,
            url=f"https://{b['host']}/hcmUI/CandidateExperience/en/sites/{b['site']}/job/{job_id}",
            title=r.get("Title", ""),
            location=r.get("PrimaryLocation") or "",
            work_mode=r.get("WorkplaceType") or "",
            posted_at=_parse_date(r.get("PostedDate")),
        ))
    return jobs, item.get("TotalJobsCount", len(jobs))


def parse_detail(data):
    item = (data.get("items") or [{}])[0]
    description = BeautifulSoup(item.get("ExternalDescriptionStr") or "", "html.parser") \
        .get_text("\n", strip=True)

    places = [w.get("LocationName") for w in item.get("workLocation", []) if w.get("LocationName")]
    flex = {f.get("Prompt", ""): f.get("Value", "") for f in item.get("requisitionFlexFields", [])}
    low, high = flex.get("Minimum Pay Range"), flex.get("Maximum Pay Range")

    employment = item.get("JobSchedule") or ""
    if str(flex.get("Is this a Contract Position?", "")).lower() == "yes":
        employment = f"{employment} Contract".strip()

    return {
        "description": description,
        "location": "; ".join(places),
        "employment_type": employment,
        "salary_text": f"{low} - {high}" if low and high else "",
        "posted_at": _parse_date(item.get("ExternalPostedStartDate")),
    }


def fetch_list(board_url, session=None, max_jobs=MAX_JOBS):
    session = session or requests.Session()
    jobs, seen, offset = [], set(), 0
    while True:
        r = session.get(_list_url(board_url, offset), headers=UA, timeout=30)
        r.raise_for_status()
        page, total = parse_list(r.json(), board_url)
        new = [j for j in page if j.source_job_id not in seen]
        seen.update(j.source_job_id for j in new)
        jobs.extend(new)
        offset += PAGE_SIZE
        # stop when everything is fetched, or the server ignored the offset (no new ids)
        if not new or offset >= total or len(jobs) >= max_jobs:
            return jobs


def fetch_detail(board_url, rec, session=None):
    session = session or requests.Session()
    b = parse_board_url(board_url)
    url = (f"{b['api_base']}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
           f"&finder=ById;Id=\"{rec.source_job_id}\",siteNumber={b['site']}")
    r = session.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_detail(r.json())
