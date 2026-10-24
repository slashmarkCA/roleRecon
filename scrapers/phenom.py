import html
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

PAGE_SIZE = 50
MAX_JOBS = 500
PAGE_ID = "page15-ds"
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
ALL_FIELDS = ["category", "country", "city", "state", "type", "phLocSlider"]


def parse_board_url(board_url):
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[-1] != "search-results":
        raise ValueError("Expected a Phenom search-results URL")
    country, language = parts[-3:-1]
    return {
        "origin": f"{parsed.scheme}://{parsed.netloc}",
        "country": country,
        "lang": f"{language}_{country}".lower(),
        "search_url": f"{parsed.scheme}://{parsed.netloc}/{country}/{language}/search-results",
        "job_base": f"{parsed.scheme}://{parsed.netloc}/{country}/{language}/job",
    }


def build_search_payload(offset=0, limit=PAGE_SIZE):
    return {
        "lang": "en_us",
        "deviceType": "desktop",
        "country": "us",
        "pageName": "search-results",
        "ddoKey": "eagerLoadRefineSearch",
        "sortBy": "",
        "subsearch": "",
        "from": offset,
        "irs": False,
        "jobs": True,
        "counts": True,
        "all_fields": ALL_FIELDS,
        "size": limit,
        "clearAll": False,
        "jdsource": "facets",
        "isSliderEnable": True,
        "pageId": PAGE_ID,
        "siteType": "external",
        "keywords": "",
        "global": True,
        "selected_fields": {"country": ["Canada"], "state": ["Ontario"]},
        "locationData": {
            "sliderRadius": 50,
            "aboveMaxRadius": True,
            "LocationUnit": "kilometers",
        },
        "s": "1",
    }


def _job_url(job_base, job):
    job_id = str(job.get("jobId") or job.get("reqId") or "").strip()
    title = str(job.get("title") or "").strip()
    if not job_id or not title:
        return ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return f"{job_base}/{quote(job_id)}/{quote(slug, safe='-')}"


def _posted_date(value):
    if not value:
        return None
    try:
        posted = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return posted if posted.tzinfo else posted.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_detail_page(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        posting = _find_job_posting(data)
        if posting is None:
            continue

        description = html.unescape(posting.get("description") or "")
        description = BeautifulSoup(description, "html.parser").get_text("\n", strip=True)
        if not description:
            raise ValueError("Phenom JobPosting data has no description")
        return {
            "description": description,
            "posted_at": _posted_date(posting.get("datePosted")),
        }
    raise ValueError("Phenom job page has no JobPosting JSON-LD data")


def _find_job_posting(data):
    if isinstance(data, list):
        for item in data:
            posting = _find_job_posting(item)
            if posting is not None:
                return posting
    elif isinstance(data, dict):
        types = data.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "JobPosting" in types:
            return data
        for key in ("@graph", "mainEntity"):
            if key in data:
                posting = _find_job_posting(data[key])
                if posting is not None:
                    return posting
    return None


def parse_search_results(data, board_url):
    board = parse_board_url(board_url)
    widget = data.get("eagerLoadRefineSearch") if isinstance(data, dict) else None
    if (
        not isinstance(widget, dict)
        or widget.get("status") != 200
        or not isinstance(widget.get("data"), dict)
    ):
        raise ValueError("Phenom response is missing successful eagerLoadRefineSearch data")
    jobs = widget["data"].get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Phenom response is missing the job list")

    records = []
    for job in jobs:
        url = _job_url(board["job_base"], job)
        if not url:
            continue
        records.append(JobRecord(
            source_job_id=str(
                job.get("jobSeqNo") or job.get("jobId") or job.get("reqId") or ""
            ),
            url=url,
            title=(job.get("title") or "").strip(),
            location=(job.get("cityStateCountry") or job.get("location") or "").strip(),
            employment_type=(job.get("type") or "").strip(),
            posted_at=_posted_date(job.get("postedDate")),
            description=(job.get("descriptionTeaser") or "").strip(),
        ))
    return records


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    headers = {
        **UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": board["origin"],
        "Referer": board["search_url"],
    }
    endpoint = f"{board['origin']}/widgets"
    records = []
    offset = 0
    total = None

    while True:
        response = session.post(
            endpoint,
            json=build_search_payload(offset=offset),
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        widget = data.get("eagerLoadRefineSearch") if isinstance(data, dict) else None
        if (
            not isinstance(widget, dict)
            or widget.get("status") != 200
            or not isinstance(widget.get("data"), dict)
            or not isinstance(widget["data"].get("jobs"), list)
        ):
            raise ValueError("Phenom search request did not return successful job data")

        if total is None:
            try:
                total = int(widget["totalHits"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Phenom search response is missing totalHits") from exc
        page = parse_search_results(data, board_url)
        records.extend(page)
        offset += PAGE_SIZE
        if not page or offset >= total or len(records) >= MAX_JOBS:
            return records[:MAX_JOBS]
        time.sleep(1)


def fetch_detail(board_url, rec, session=None):
    session = session or requests.Session()
    board = parse_board_url(board_url)
    response = session.get(
        rec.url,
        headers={**UA, "Accept": "text/html", "Referer": board["search_url"]},
        timeout=30,
    )
    response.raise_for_status()
    return parse_detail_page(response.content)
