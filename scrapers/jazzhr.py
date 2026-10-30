import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}


def parse_board_url(board_url):
    parsed = urlparse(board_url)
    hostname = parsed.hostname or ""
    suffix = ".applytojob.com"
    if not hostname.endswith(suffix) or not hostname[:-len(suffix)]:
        raise ValueError("Expected a JazzHR board URL like <account>.applytojob.com/apply")
    return {
        "hostname": hostname,
        "list_url": f"https://{hostname}/apply",
    }


def _clean_text(value):
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.replace("\xa0", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def parse_job_list(page_html, board_url):
    board = parse_board_url(board_url)
    soup = BeautifulSoup(page_html, "html.parser")
    container = soup.select_one(".jobs-list")
    if container is None:
        raise ValueError("JazzHR response is missing the expected jobs list")

    records = []
    for card in container.select("li.list-group-item"):
        link = card.select_one("h3.list-group-item-heading a[href]")
        if link is None:
            continue
        url = urljoin(f"https://{board['hostname']}/", link["href"])
        parsed_url = urlparse(url)
        parts = [part for part in parsed_url.path.split("/") if part]
        if (
            parsed_url.hostname != board["hostname"]
            or len(parts) < 2
            or parts[0] != "apply"
        ):
            continue

        location = ""
        for item in card.select(".list-inline.list-group-item-text li"):
            if item.select_one(".fa-map-marker"):
                location = item.get_text(" ", strip=True)
                break

        title = link.get_text(" ", strip=True)
        if title:
            records.append(JobRecord(
                source_job_id=parts[1],
                url=url,
                title=title,
                location=location,
            ))
    return records


def parse_job_detail(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    description = soup.select_one("#job-description")
    if description is None:
        raise ValueError("JazzHR posting is missing its job description")
    text = _clean_text(description.get_text("\n", strip=True))
    if not text:
        raise ValueError("JazzHR posting has an empty job description")
    return {"description": text}


def fetch_list(board_url, session=None, options=None):
    session = session or requests.Session()
    response = session.get(
        parse_board_url(board_url)["list_url"],
        headers=UA,
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_list(response.text, board_url)


def fetch_detail(board_url, rec, session=None, options=None):
    parse_board_url(board_url)
    session = session or requests.Session()
    response = session.get(rec.url, headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_detail(response.text)
