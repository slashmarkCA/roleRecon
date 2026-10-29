import json
import re
from email.utils import parsedate_to_datetime
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
CATEGORY_PATH = re.compile(r"/Category-Page-[^/]+/(\d+)/?")
JOB_ID = re.compile(r"/(\d+)/?$")
TITLE_LOCATION = re.compile(r"^(.*?)\s+\(([^()]*(?:,[^()]*)+)\)\s*$")
PAGE_SIZE = 25
MAX_JOBS = 500
RECRUITING_API_PATH = "/services/recruiting/v1/jobs"
RECRUITING_PAGE_SIZE = 10


def _is_search_page(path):
    """Return whether a SuccessFactors path identifies a search-results page."""
    return path.rstrip("/").lower().endswith("/search")


def _is_widget_search_page(page_html):
    return "xweb/rmk-jobs-search" in page_html


def _widget_locale(page_html):
    match = re.search(r"\bcurrentLocale\s*:\s*['\"]([^'\"]+)['\"]", page_html)
    if not match:
        raise ValueError("SuccessFactors widget page is missing its current locale")
    return match.group(1)


def build_recruiting_payload(board_url, page_number, locale):
    """Build the public Recruiting Marketing search request from board filters."""
    query = dict(parse_qsl(urlparse(board_url).query, keep_blank_values=True))
    try:
        facet_filters = json.loads(query.get("facetFilters", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("SuccessFactors facetFilters must contain valid JSON") from exc
    if not isinstance(facet_filters, dict):
        raise ValueError("SuccessFactors facetFilters must be a JSON object")

    return {
        "locale": locale,
        "pageNumber": page_number,
        "sortBy": query.get("sortBy", ""),
        "keywords": query.get("q", ""),
        "location": query.get("locationsearch", ""),
        "facetFilters": facet_filters,
        "brand": query.get("brand", ""),
        "skills": [],
        "categoryId": 0,
        "alertId": "",
        "rcmCandidateId": "",
    }


def parse_recruiting_results(data, board_url, locale):
    """Parse the public SuccessFactors Recruiting Marketing jobs response."""
    if not isinstance(data, dict) or not isinstance(data.get("jobSearchResult"), list):
        raise ValueError("SuccessFactors recruiting response is missing its job list")

    parsed_board = urlparse(board_url)
    records = []
    for item in data["jobSearchResult"]:
        job = item.get("response") if isinstance(item, dict) else None
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or "").strip()
        title = str(job.get("unifiedStandardTitle") or "").strip()
        url_title = str(job.get("unifiedUrlTitle") or job.get("urlTitle") or "").strip()
        if not job_id or not title or not url_title:
            continue

        slug = quote(unquote(url_title), safe="-")
        locations = job.get("jobLocationShort") or []
        if isinstance(locations, str):
            locations = [locations]
        location = ", ".join(
            value.strip() for value in locations if isinstance(value, str) and value.strip()
        )
        posted_at = None
        start_date = job.get("unifiedStandardStart")
        if start_date:
            try:
                posted_at = datetime.strptime(start_date, "%d/%m/%Y").replace(
                    tzinfo=timezone.utc
                )
            except (TypeError, ValueError):
                pass

        records.append(JobRecord(
            source_job_id=job_id,
            url=f"{parsed_board.scheme}://{parsed_board.netloc}/job/{slug}/{job_id}-{locale}",
            title=title,
            location=location,
            posted_at=posted_at,
        ))
    return records


def fetch_recruiting_list(board_url, session, page_html):
    parsed_board = urlparse(board_url)
    locale = _widget_locale(page_html)
    endpoint = f"{parsed_board.scheme}://{parsed_board.netloc}{RECRUITING_API_PATH}"
    headers = {
        **UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": f"{parsed_board.scheme}://{parsed_board.netloc}",
        "Referer": board_url,
    }
    query = dict(parse_qsl(parsed_board.query, keep_blank_values=True))
    try:
        page_number = int(query.get("pageNumber", "0"))
    except ValueError as exc:
        raise ValueError("SuccessFactors pageNumber must be an integer") from exc

    records = []
    total = None
    while len(records) < MAX_JOBS:
        response = session.post(
            endpoint,
            json=build_recruiting_payload(board_url, page_number, locale),
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("jobSearchResult"), list):
            raise ValueError("SuccessFactors recruiting request did not return job data")
        if total is None:
            try:
                total = int(data["totalJobs"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "SuccessFactors recruiting response is missing totalJobs"
                ) from exc

        page = parse_recruiting_results(data, board_url, locale)
        if data["jobSearchResult"] and not page:
            raise ValueError("SuccessFactors recruiting response contains no valid jobs")
        records.extend(page)
        if not data["jobSearchResult"] or len(records) >= total:
            break
        page_number += 1
        if len(records) < MAX_JOBS:
            time.sleep(1)
    return records[:MAX_JOBS]


def feed_url(board_url):
    """Convert a SuccessFactors category page to its public RSS category feed."""
    parsed = urlparse(board_url)
    if parsed.path.rstrip("/") == "/services/rss/category":
        return board_url

    match = CATEGORY_PATH.search(parsed.path)
    if not match:
        raise ValueError("Expected a SuccessFactors category page or RSS category feed URL")

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        "/services/rss/category/",
        "",
        urlencode({"catid": match.group(1)}),
        "",
    ))


def parse_search_results(page_html, board_url):
    """Parse a SuccessFactors HTML search-results page."""
    parsed_board = urlparse(board_url)
    if not _is_search_page(parsed_board.path):
        raise ValueError("Expected a SuccessFactors search-results URL")

    soup = BeautifulSoup(page_html, "html.parser")
    table = soup.select_one("#searchresults")
    if table is None:
        raise ValueError("SuccessFactors search response is missing its results table")

    records = []
    for row in table.select("tr"):
        link = row.select_one("td.colTitle a[href*='/job/']")
        if link is None:
            continue
        url = urljoin(f"{parsed_board.scheme}://{parsed_board.netloc}", link.get("href", ""))
        parsed_url = urlparse(url)
        match = JOB_ID.search(parsed_url.path)
        if not match or parsed_url.netloc.lower() != parsed_board.netloc.lower():
            continue

        location = row.select_one("td.colLocation")
        posted = row.select_one("td.colDate")
        posted_at = None
        if posted:
            try:
                posted_at = datetime.strptime(
                    posted.get_text(" ", strip=True), "%b %d, %Y"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        records.append(JobRecord(
            source_job_id=match.group(1),
            url=url,
            title=link.get_text(" ", strip=True),
            location=location.get_text(" ", strip=True) if location else "",
            posted_at=posted_at,
        ))
    return records


def parse_search_detail(page_html):
    """Parse a SuccessFactors job detail page into plain text."""
    soup = BeautifulSoup(page_html, "html.parser")
    description = soup.select_one(".jobdescription")
    if description is not None:
        text = description.get_text("\n", strip=True)
        if not text:
            raise ValueError("SuccessFactors job page has an empty description")
        return {"description": text}

    job = soup.select_one(".job")
    sections = job.select(".joblayouttoken") if job else []
    description_sections = []
    in_description = False
    for section in sections:
        section_text = section.get_text("\n", strip=True)
        if section_text.startswith("Job Overview"):
            in_description = True
        if in_description and section_text:
            description_sections.append(section_text)
    text = "\n\n".join(description_sections)
    if not text:
        raise ValueError("SuccessFactors job page is missing its description")
        raise ValueError("SuccessFactors job page has an empty description")
    return {"description": text}


def _title_and_location(value):
    title = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    match = TITLE_LOCATION.fullmatch(title)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return title, ""


def _date(value):
    try:
        return parsedate_to_datetime(value) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_feed(data):
    """Parse the public SuccessFactors RSS feed, which includes full job descriptions."""
    root = ET.fromstring(data)
    records = []
    for item in root.findall("./channel/item"):
        url = (item.findtext("link") or "").strip()
        if not url:
            continue

        title, location = _title_and_location(item.findtext("title") or "")
        description = BeautifulSoup(
            item.findtext("description") or "", "html.parser"
        ).get_text("\n", strip=True)
        path = urlparse(url).path.rstrip("/")
        id_match = JOB_ID.search(path)
        records.append(JobRecord(
            source_job_id=id_match.group(1) if id_match else url,
            url=url,
            title=title,
            location=location,
            posted_at=_date(item.findtext("pubDate")),
            description=description,
        ))
    return records


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    parsed = urlparse(board_url)
    if not _is_search_page(parsed.path):
        response = session.get(feed_url(board_url), headers=UA, timeout=30)
        response.raise_for_status()
        return parse_feed(response.content)

    first_response = session.get(board_url, headers=UA, timeout=30)
    first_response.raise_for_status()
    if _is_widget_search_page(first_response.text):
        return fetch_recruiting_list(board_url, session, first_response.text)

    records = []
    offset = 0
    while len(records) < MAX_JOBS:
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "startrow"
        ]
        if offset:
            query.append(("startrow", str(offset)))
        if offset:
            page_url = urlunparse(parsed._replace(query=urlencode(query)))
            response = session.get(page_url, headers=UA, timeout=30)
            response.raise_for_status()
        else:
            response = first_response
        page = parse_search_results(response.text, board_url)
        records.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if len(records) < MAX_JOBS:
            time.sleep(1)
    return records[:MAX_JOBS]


def fetch_detail(board_url, rec, session=None):
    if rec.description:
        return {}
    board_host = urlparse(board_url).netloc.lower()
    detail_url = urlparse(rec.url)
    if detail_url.netloc.lower() != board_host:
        raise ValueError("SuccessFactors job URL does not match the selected board")
    session = session or requests.Session()
    response = session.get(rec.url, headers=UA, timeout=30)
    response.raise_for_status()
    return parse_search_detail(response.text)
