import re
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}

# The eRecruit "RSS.aspx" feed is malformed: it opens a pile of empty <item> tags, closes the
# <rss> document, and then the real postings follow as plain markup in an HTML block. Each posting
# is <h1>title</h1><description>html</description><link>url</link><pubDate>date</pubDate>, so
# they are read with a pattern, not with an XML parser.
ITEM = re.compile(
    r"<h1>(.*?)</h1>\s*<description>(.*?)</description>\s*<link>(.*?)</link>"
    r"(?:\s*<pubDate>(.*?)</pubDate>)?",
    re.S | re.I,
)


def feed_url(board_url):
    """Accept either the RSS.aspx URL itself or any URL under the site's /erecruit/ folder."""
    if board_url.lower().split("?")[0].endswith("rss.aspx"):
        return board_url
    u = urlparse(board_url)
    return f"{u.scheme}://{u.netloc}/erecruit/RSS.aspx"


def _decode(data):
    # The feed declares Windows-1252 but may actually send UTF-8; accept both.
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _field(description_html, label):
    """Read '<i>Label:</i> value<br>' lines from the posting's description."""
    m = re.search(rf"<i>\s*{re.escape(label)}:\s*</i>\s*(.*?)\s*<br", description_html, re.S | re.I)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def _parse_date(value):
    try:
        return parsedate_to_datetime((value or "").strip())
    except (TypeError, ValueError):
        return None


def parse_feed(data, board_url=""):
    """Turn the feed (str or bytes) into JobRecords. The feed already contains each
    posting's full description, so no detail request is needed."""
    text = data if isinstance(data, str) else _decode(data)
    jobs = []
    for title, description, link, pub in ITEM.findall(text):
        link = link.strip()
        m = re.search(r"VacancyUID=(\w+)", link)
        jobs.append(JobRecord(
            source_job_id=m.group(1) if m else link,
            url=link,
            title=BeautifulSoup(title, "html.parser").get_text(" ", strip=True),
            location=_field(description, "Location"),
            employment_type=_field(description, "Status"),
            salary_text=_field(description, "Wage Schedule"),
            posted_at=_parse_date(pub),
            description=BeautifulSoup(description, "html.parser").get_text("\n", strip=True),
        ))
    return jobs


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    r = session.get(feed_url(board_url), headers=UA, timeout=60)
    r.raise_for_status()
    return parse_feed(r.content, board_url)


def fetch_detail(board_url, rec, session=None):
    return {}  # the feed already includes the full description
