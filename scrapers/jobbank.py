import re
from datetime import datetime
from xml.etree import ElementTree as ET

import requests

from .base import JobRecord

ATOM = {"a": "http://www.w3.org/2005/Atom"}
# Job Bank blocks curl-style clients; a browser-style User-Agent is needed.
UA = {"User-Agent": "Mozilla/5.0 (compatible; roleRecon/0.1; personal job-search tool)"}
FIELD = re.compile(r"<strong>(.*?):</strong>\s*(.*?)\s*(?:<br\s*/?>|$)", re.I | re.S)


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_feed(xml, board_url=""):
    """Parse Job Bank's Atom feed (str or bytes) into JobRecords. Each entry has a title,
    a link, an updated time, and a summary holding Job number / Location / Employer / Salary."""
    root = ET.fromstring(xml)
    jobs = []
    for e in root.findall("a:entry", ATOM):
        link = e.find("a:link", ATOM)
        url = link.get("href") if link is not None else ""
        if not url:
            continue
        summary = e.findtext("a:summary", default="", namespaces=ATOM)
        fields = {k.strip().lower(): re.sub(r"<[^>]+>", "", v).strip()
                  for k, v in FIELD.findall(summary)}
        jobs.append(JobRecord(
            source_job_id=url.rstrip("/").rsplit("/", 1)[-1],
            url=url,
            title=e.findtext("a:title", default="", namespaces=ATOM).strip(),
            company=fields.get("employer", ""),
            location=fields.get("location", ""),
            salary_text=fields.get("salary", ""),
            posted_at=_parse_dt(e.findtext("a:updated", default="", namespaces=ATOM)),
        ))
    return jobs


def list_limit(board_url):
    """The feed returns at most its `rows` parameter's worth of entries (None if not set)."""
    m = re.search(r"[?&]rows=(\d+)", board_url)
    return int(m.group(1)) if m else None


def fetch_list(board_url, session=None):
    """board_url is the full Job Bank feed URL (with its query string)."""
    session = session or requests.Session()
    r = session.get(board_url, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_feed(r.content, board_url)


def fetch_detail(board_url, rec, session=None):
    return {}  # the feed has no description; the posting page would need separate parsing
