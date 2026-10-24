import re
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
CATEGORY_PATH = re.compile(r"/Category-Page-[^/]+/(\d+)/?")
JOB_ID = re.compile(r"/(\d+)/?$")
TITLE_LOCATION = re.compile(r"^(.*?)\s+\(([^()]*(?:,[^()]*)+)\)\s*$")


def feed_url(board_url):
    """Accept a SuccessFactors category page or its RSS category feed URL."""
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
    response = session.get(feed_url(board_url), headers=UA, timeout=30)
    response.raise_for_status()
    return parse_feed(response.content)


def fetch_detail(board_url, rec, session=None):
    return {}
