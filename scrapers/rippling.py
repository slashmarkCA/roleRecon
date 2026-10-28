import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
MAX_JOBS = 1000
LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2}|-\d{3})?$")


def parse_board_url(board_url):
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname != "ats.rippling.com" or len(parts) < 2 or parts[-1] != "jobs":
        raise ValueError("Expected a Rippling board URL like ats.rippling.com/<board>/jobs")

    slug = parts[-2]
    locale = parts[-3] if len(parts) >= 3 and LOCALE.fullmatch(parts[-3]) else ""
    prefix = f"/{locale}/{slug}" if locale else f"/{slug}"
    return {
        "slug": slug,
        "path_prefix": prefix,
        "list_url": f"https://ats.rippling.com{prefix}/jobs?{urlencode({'pageSize': MAX_JOBS})}",
    }


def _next_data(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None:
        raise ValueError("Rippling response is missing its Next.js page data")
    try:
        return json.loads(script.string or script.get_text())
    except json.JSONDecodeError as exc:
        raise ValueError("Rippling response contains invalid Next.js page data") from exc


def _page_props(page_html):
    data = _next_data(page_html)
    props = data.get("props", {}).get("pageProps")
    if not isinstance(props, dict):
        raise ValueError("Rippling response is missing page properties")
    return props


def _job_posts(page_html, slug):
    props = _page_props(page_html)
    api_data = props.get("apiData", {})
    if api_data.get("jobBoardSlug") not in {None, slug}:
        raise ValueError("Rippling response does not match the requested board")

    queries = props.get("dehydratedState", {}).get("queries", [])
    for query in queries:
        key = query.get("queryKey", [])
        if len(key) >= 3 and key[:3] == ["board", slug, "job-posts"]:
            data = query.get("state", {}).get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
    raise ValueError("Rippling response is missing its job listings")


def _location_fields(locations):
    names = []
    modes = []
    for location in locations if isinstance(locations, list) else []:
        if isinstance(location, str):
            name = location.strip()
            workplace = ""
        elif isinstance(location, dict):
            name = str(location.get("name") or "").strip()
            if not name:
                name = ", ".join(
                    str(location.get(field)).strip()
                    for field in ("city", "state", "country")
                    if location.get(field)
                )
            workplace = str(location.get("workplaceType") or "")
        else:
            continue
        if name and name not in names:
            names.append(name)
        normalized = workplace.upper().replace("-", "_")
        mode = {
            "REMOTE": "Remote",
            "ON_SITE": "On-site",
            "HYBRID": "Hybrid",
        }.get(normalized, "")
        if mode and mode not in modes:
            modes.append(mode)
    return "; ".join(names), ", ".join(modes)


def _parse_date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def parse_job_list(page_html, board_url):
    board = parse_board_url(board_url)
    items = _job_posts(page_html, board["slug"])
    records = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Rippling job list contains an invalid entry")
        job_id = str(item.get("id") or "").strip()
        title = str(item.get("name") or "").strip()
        if not job_id or not title:
            raise ValueError("Rippling job is missing its id or title")
        location, work_mode = _location_fields(item.get("locations"))
        records.append(JobRecord(
            source_job_id=job_id,
            url=f"https://ats.rippling.com{board['path_prefix']}/jobs/{job_id}",
            title=title,
            location=location,
            work_mode=work_mode,
        ))
    return records


def _html_to_text(value):
    soup = BeautifulSoup(value or "", "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    text = soup.get_text("\n", strip=True).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_job_detail(page_html, board_url):
    board = parse_board_url(board_url)
    api_data = _page_props(page_html).get("apiData", {})
    if api_data.get("jobBoard", {}).get("slug") not in {None, board["slug"]}:
        raise ValueError("Rippling posting does not match the requested board")
    job = api_data.get("jobPost")
    if not isinstance(job, dict):
        raise ValueError("Rippling response is missing its job posting")

    description_parts = job.get("description", {})
    if isinstance(description_parts, dict):
        description = "\n\n".join(
            text for text in (
                _html_to_text(description_parts.get("company")),
                _html_to_text(description_parts.get("role")),
            ) if text
        )
    else:
        description = _html_to_text(description_parts)
    if not description:
        raise ValueError("Rippling posting has an empty description")

    location, work_mode = _location_fields(job.get("workLocations"))
    if not work_mode:
        pay_ranges = job.get("payRangeDetails")
        if isinstance(pay_ranges, list) and any(
            isinstance(item, dict) and item.get("isRemote") for item in pay_ranges
        ):
            work_mode = "Remote"

    employment = job.get("employmentType")
    if isinstance(employment, dict):
        employment = employment.get("label", "")
    return {
        "description": description,
        "location": location,
        "work_mode": work_mode,
        "employment_type": str(employment or ""),
        "posted_at": _parse_date(job.get("createdOn")),
    }


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    response = session.get(
        parse_board_url(board_url)["list_url"],
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_list(response.text, board_url)


def fetch_detail(board_url, rec, session=None):
    parse_board_url(board_url)
    session = session or requests.Session()
    response = session.get(rec.url, headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_detail(response.text, board_url)
