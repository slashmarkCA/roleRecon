import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

MAX_JOBS = 500
UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
DETAIL_PATH = re.compile(r"/JobDetail/(\d+)/?", re.IGNORECASE)


def parse_board_url(board_url):
    """Validate an Avature SearchJobs URL and return its portal details."""
    parsed = urlparse(board_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.path.rstrip("/").lower().endswith("/searchjobs")
    ):
        raise ValueError("Expected an Avature SearchJobs URL")
    return {
        "host": parsed.netloc,
        "origin": f"{parsed.scheme}://{parsed.netloc}",
        "search_path": parsed.path.rstrip("/"),
        "search_url": board_url,
    }


def parse_search_results(page_html, board_url):
    """Parse Avature job cards into standard job records."""
    board = parse_board_url(board_url)
    soup = BeautifulSoup(page_html, "html.parser")
    if soup.select_one(".results") is None:
        raise ValueError("Avature search response is missing its results")
    records = []
    for article in soup.select("article.article--result"):
        link = next(
            (
                anchor for anchor in article.find_all("a", href=True)
                if DETAIL_PATH.search(urlparse(anchor["href"]).path)
            ),
            None,
        )
        if link is None:
            continue
        url = urljoin(board["origin"], link["href"])
        parsed_url = urlparse(url)
        match = DETAIL_PATH.search(parsed_url.path)
        if match is None or parsed_url.netloc != board["host"]:
            continue
        location = article.select_one(".list-item-location")
        location_text = location.get_text(" ", strip=True) if location else ""
        location_text = re.sub(r"\s*,\s*", ", ", location_text)
        records.append(JobRecord(
            source_job_id=match.group(1),
            url=url,
            title=link.get_text(" ", strip=True),
            location=location_text,
        ))
    return records


def next_page_url(page_html, current_url):
    """Return the Avature next-page URL, if the current page has one."""
    current = urlparse(current_url)
    soup = BeautifulSoup(page_html, "html.parser")
    for link in soup.find_all("a", href=True):
        label = link.get_text(" ", strip=True).lower()
        if label not in {"next", "next >>", "»"}:
            continue
        candidate = urljoin(current_url, link["href"])
        parsed = urlparse(candidate)
        if parsed.netloc == current.netloc and parsed.path.rstrip("/") == current.path.rstrip("/"):
            return candidate
    return None


def parse_job_detail(page_html):
    """Extract plain-text job description and metadata from an Avature detail page."""
    soup = BeautifulSoup(page_html, "html.parser")
    article = next(
        (
            section for section in soup.select("article.article--details")
            if (
                section.select_one(".article__content")
                and not any(
                    class_name.startswith("regular-fields")
                    for class_name in section.get("class", [])
                )
            )
        ),
        None,
    )
    if article is None:
        raise ValueError("Avature job page is missing its description")
    values = article.select(".article__content__view__field__value")
    if not values:
        raise ValueError("Avature job page is missing its description")
    description = values[0].get_text("\n", strip=True)
    if not description:
        raise ValueError("Avature job page has an empty description")
    return {"description": description}


def fetch_list(board_url, session=None, options=None):
    session = session or requests.Session()
    current_url = parse_board_url(board_url)["search_url"]
    records = []
    seen_urls = set()
    while current_url not in seen_urls and len(records) < MAX_JOBS:
        seen_urls.add(current_url)
        response = session.get(current_url, headers=UA, timeout=30)
        response.raise_for_status()
        page = response.text
        records.extend(parse_search_results(page, board_url))
        following_page = next_page_url(page, current_url)
        if not following_page:
            break
        current_url = following_page
        if len(records) < MAX_JOBS:
            time.sleep(1)
    return records[:MAX_JOBS]


def fetch_detail(board_url, rec, session=None, options=None):
    board = parse_board_url(board_url)
    parsed_url = urlparse(rec.url)
    if parsed_url.netloc != board["host"] or DETAIL_PATH.search(parsed_url.path) is None:
        raise ValueError("Avature job URL does not match the selected portal")
    session = session or requests.Session()
    response = session.get(rec.url, headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_detail(response.text)
