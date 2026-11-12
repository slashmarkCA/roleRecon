import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
ROOT = "https://www.pulsecrafttechnologies.com"
BOARD_PATH = "/careers"
POSTING_PATH = re.compile(r"^/careers/([a-z0-9-]+)/?$")
POSTED_DATE = re.compile(r"\bPosted\s+(\d{4}-\d{2}-\d{2})\b")


def parse_board_url(board_url):
    """Validate the public PulseCraft careers page URL."""
    parsed = urlparse(board_url)
    if (
        parsed.netloc.lower() not in {"www.pulsecrafttechnologies.com", "pulsecrafttechnologies.com"}
        or parsed.path.rstrip("/") != BOARD_PATH
    ):
        raise ValueError("Expected the PulseCraft careers URL at /careers")
    return f"{ROOT}{BOARD_PATH}"


def _posting_url(href):
    url = urlparse(urljoin(ROOT, href))
    match = POSTING_PATH.fullmatch(url.path)
    if url.netloc.lower() != "www.pulsecrafttechnologies.com" or not match:
        return None
    return url.geturl().split("?", 1)[0].split("#", 1)[0], match.group(1)


def _work_mode(value):
    normalized = value.lower()
    if "hybrid" in normalized:
        return "Hybrid"
    if "remote" in normalized:
        return "Remote"
    if "on-site" in normalized or "onsite" in normalized:
        return "On-site"
    return ""


def parse_job_list(page_html, board_url):
    parse_board_url(board_url)
    soup = BeautifulSoup(page_html, "html.parser")
    records = []
    seen = set()

    for link in soup.select('a[href^="/careers/"]'):
        if link.get_text(" ", strip=True).lower() != "view & apply":
            continue
        posting = _posting_url(link.get("href", ""))
        if not posting:
            continue
        url, job_id = posting
        if job_id in seen:
            continue
        card = link.find_parent("div", class_="rounded-2xl")
        title_element = card.select_one("h3") if card else None
        if not card or not title_element:
            continue
        title = title_element.get_text(" ", strip=True)
        if not title:
            continue
        text_nodes = [
            re.sub(r"\s+", " ", str(text)).strip()
            for text in card.find_all(string=True)
            if str(text).strip()
        ]
        title_index = text_nodes.index(title) if title in text_nodes else -1
        employment_type = text_nodes[title_index - 1] if title_index > 0 else ""
        raw_location = text_nodes[title_index + 1] if title_index >= 0 and title_index + 1 < len(text_nodes) else ""
        location = raw_location.split(" (", 1)[0].strip()
        records.append(JobRecord(
            source_job_id=job_id,
            url=url,
            title=title,
            location=location,
            work_mode=_work_mode(raw_location),
            employment_type=employment_type,
        ))
        seen.add(job_id)

    if not records:
        raise ValueError("PulseCraft page is missing the expected public job cards")
    return records


def parse_job_detail(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    main = soup.find("main")
    title_element = main.find("h1") if main else None
    if not main or not title_element:
        raise ValueError("PulseCraft job page is missing its main heading")

    lines = [line.strip() for line in main.get_text("\n", strip=True).splitlines() if line.strip()]
    try:
        start = lines.index("Role Overview") + 1
        end = lines.index("Submit Your Application", start)
    except ValueError as exc:
        raise ValueError("PulseCraft job page is missing its description sections") from exc
    description = "\n".join(lines[start:end]).strip()
    if not description:
        raise ValueError("PulseCraft job page has an empty description")

    posted_match = POSTED_DATE.search(" ".join(lines))
    detail = {
        "title": title_element.get_text(" ", strip=True),
        "description": description,
    }
    if posted_match:
        detail["posted_at"] = datetime.strptime(
            posted_match.group(1), "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)
    return detail


def fetch_list(board_url, session=None, options=None):
    session = session or requests.Session()
    response = session.get(
        parse_board_url(board_url),
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_list(response.text, board_url)


def fetch_detail(board_url, rec, session=None, options=None):
    parse_board_url(board_url)
    posting = _posting_url(rec.url)
    if not posting:
        raise ValueError("PulseCraft detail URL must be a public careers posting")
    session = session or requests.Session()
    response = session.get(posting[0], headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_detail(response.text)
