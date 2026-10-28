import re
from email.utils import parsedate_to_datetime
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
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
    if parsed_board.path.rstrip("/") != "/search":
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
    if description is None:
        raise ValueError("SuccessFactors job page is missing its description")
    text = description.get_text("\n", strip=True)
    if not text:
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
    if parsed.path.rstrip("/") != "/search":
        response = session.get(feed_url(board_url), headers=UA, timeout=30)
        response.raise_for_status()
        return parse_feed(response.content)

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
        page_url = urlunparse(parsed._replace(query=urlencode(query)))
        response = session.get(page_url, headers=UA, timeout=30)
        response.raise_for_status()
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
