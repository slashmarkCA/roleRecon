import html
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

UA = {"User-Agent": "roleRecon/0.1 (personal job-search tool)"}
ARRANGEMENT = re.compile(r"\s*\((remote|hybrid|on[- ]site)\)\s*$", re.IGNORECASE)
DETAIL_LINK = re.compile(r"\[View\]\((https://[^)]+/jobs/view/([^)]+)\.md)\)")


def parse_board_url(board_url):
    """Return the Workable account slug and canonical board URL."""
    parsed = urlparse(board_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "apply.workable.com" or not parts:
        raise ValueError("Expected a Workable board URL like apply.workable.com/<account>")
    slug = parts[0]
    query = urlencode(parse_qsl(parsed.query, keep_blank_values=True))
    return {
        "slug": slug,
        "board_url": f"https://apply.workable.com/{slug}/",
        "list_url": f"https://apply.workable.com/{slug}/jobs.md"
        + (f"?{query}" if query else ""),
    }


def _clean_cell(value):
    return re.sub(r"\s+", " ", value.strip())


def _location_and_mode(value):
    location = _clean_cell(value)
    match = ARRANGEMENT.search(location)
    if not match:
        return location, ""
    mode = match.group(1).replace("-", " ").title()
    return location[:match.start()].strip(), mode


def _parse_date(value):
    if not value or value.strip() in {"—", "-"}:
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def parse_job_list(markdown, board_url):
    """Parse Workable's public jobs.md Markdown table."""
    parse_board_url(board_url)
    records = []
    found_header = False
    for line in markdown.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[0].lower() == "title":
            found_header = True
            continue
        if len(cells) != 7 or cells[0].lower() == "-------":
            continue
        title, _department, raw_location, job_type, salary, posted, details = cells
        link = DETAIL_LINK.fullmatch(details)
        if not link or not title:
            continue
        parsed_link = urlparse(link.group(1))
        expected = parse_board_url(board_url)
        if (
            parsed_link.netloc.lower() != "apply.workable.com"
            or not parsed_link.path.startswith(f"/{expected['slug']}/jobs/view/")
        ):
            continue
        location, work_mode = _location_and_mode(raw_location)
        records.append(JobRecord(
            source_job_id=link.group(2),
            url=link.group(1),
            title=title,
            location=location,
            work_mode=work_mode,
            employment_type="" if job_type in {"—", "-"} else job_type,
            salary_text="" if salary in {"—", "-"} else salary,
            posted_at=_parse_date(posted),
        ))
    if not found_header:
        raise ValueError("Workable response is missing the expected jobs table")
    return records


def _markdown_to_text(markdown):
    text = html.unescape(markdown)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(?<!\w)(?:\*\*|__)(.+?)(?:\*\*|__)(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "- ", text)
    text = BeautifulSoup(text, "html.parser").get_text("\n")
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip()


def parse_job_detail(markdown):
    """Extract posting fields and plain-text description from a Workable .md detail page."""
    lines = markdown.splitlines()
    title = ""
    fields = {}
    description_lines = []
    in_description = False
    metadata = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
        elif stripped.startswith("> ") and not metadata:
            metadata = stripped[2:].strip()
        elif stripped.startswith("**") and ":**" in stripped:
            label, value = stripped[2:].split(":**", 1)
            fields[label.strip().lower()] = value.strip()
        elif stripped == "## Description":
            in_description = True
        elif in_description and stripped.startswith("## "):
            break
        elif in_description:
            description_lines.append(line)

    if "workplace" not in fields:
        mode_match = ARRANGEMENT.search(metadata)
        if mode_match:
            fields["workplace"] = mode_match.group(1)
    if "type" not in fields:
        type_match = re.search(r"·\s*([^·]+?)\s*·\s*Posted\s+", metadata)
        if type_match:
            fields["type"] = type_match.group(1).strip()
    posted_match = re.search(r"\bPosted\s+(\d{4}-\d{2}-\d{2})\b", metadata)
    metadata_parts = [part.strip() for part in metadata.split("·")]
    location = metadata_parts[1] if len(metadata_parts) >= 3 else ""
    location_mode = ARRANGEMENT.search(location)
    if location_mode:
        if "workplace" not in fields:
            fields["workplace"] = location_mode.group(1)
        location = location[:location_mode.start()].strip()

    workplace = fields.get("workplace", "").strip().lower().replace("_", "-")
    if workplace in {"on-site", "onsite"}:
        work_mode = "On-site"
    elif workplace in {"remote", "hybrid"}:
        work_mode = workplace.title()
    else:
        work_mode = workplace.replace("-", " ").title()

    description = _markdown_to_text("\n".join(description_lines))
    if not in_description or not description:
        raise ValueError("Workable job detail is missing its description")
    detail = {
        "description": description,
        "work_mode": work_mode,
        "employment_type": fields.get("type", ""),
        "salary_text": fields.get("salary", ""),
    }
    if location:
        detail["location"] = location
    if posted_match:
        detail["posted_at"] = _parse_date(posted_match.group(1))
    if title:
        detail["title"] = title
    return detail


def fetch_list(board_url, session=None):
    session = session or requests.Session()
    list_url = parse_board_url(board_url)["list_url"]
    response = session.get(list_url, headers=UA, timeout=30)
    response.raise_for_status()
    return parse_job_list(response.text, board_url)


def fetch_detail(board_url, rec, session=None):
    parse_board_url(board_url)
    session = session or requests.Session()
    response = session.get(
        rec.url,
        headers={**UA, "Accept": "text/markdown, text/plain"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_job_detail(response.text)
