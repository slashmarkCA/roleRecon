import html
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import JobRecord

API = "https://api.openwebninja.com/jsearch/search-v2"
MAX_QUERIES = 20
MAX_PAGES = 3
MAX_REQUEST_CREDITS = 30


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return str(value.get("display_name") or value.get("name") or "")
    return str(value)


def _pick(data, *keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return ""


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _description_text(value):
    raw = html.unescape(_text(value))
    return BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)


def _results(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSearch response must be a JSON object")
    data = payload.get("data", payload.get("results", []))
    if isinstance(data, dict):
        data = data.get("jobs", data.get("results", []))
    if not isinstance(data, list):
        raise ValueError("JSearch response does not contain a jobs list")
    return data


def parse_search_results(payload):
    records = []
    seen_ids = set()
    seen_urls = set()
    for item in _results(payload):
        if not isinstance(item, dict):
            raise ValueError("JSearch returned a job that is not an object")

        title = _text(_pick(item, "job_title", "title")).strip()
        url = _text(_pick(item, "job_apply_link", "job_google_link", "job_url", "url")).strip()
        if not title or not url:
            raise ValueError("JSearch job is missing its title or application URL")

        job_id = _text(_pick(item, "job_id", "id")).strip()
        normalized_url = url.rstrip("/").casefold()
        if (job_id and job_id in seen_ids) or normalized_url in seen_urls:
            continue
        if job_id:
            seen_ids.add(job_id)
        seen_urls.add(normalized_url)

        location = _text(_pick(item, "job_location", "location")).strip()
        if not location:
            location = ", ".join(
                filter(
                    None,
                    (
                        _text(_pick(item, "job_city", "city")).strip(),
                        _text(_pick(item, "job_state", "state")).strip(),
                        _text(_pick(item, "job_country", "country")).strip(),
                    ),
                )
            )

        remote_value = _pick(item, "job_is_remote", "remote")
        is_remote = remote_value is True or _text(remote_value).casefold() in {
            "true",
            "yes",
            "remote",
        }
        records.append(
            JobRecord(
                source_job_id=job_id,
                url=url,
                title=title,
                company=_text(_pick(item, "employer_name", "company_name", "company")).strip(),
                location=location,
                work_mode="Remote" if is_remote else "",
                employment_type=_text(
                    _pick(item, "job_employment_types", "job_employment_type", "employment_type")
                ),
                salary_text=_text(
                    _pick(item, "job_salary", "job_salary_string", "job_min_salary")
                ),
                posted_at=_parse_datetime(
                    _pick(item, "job_posted_at_datetime_utc", "job_posted_at", "created")
                ),
                description=_description_text(
                    _pick(item, "job_description", "description")
                ),
            )
        )
    return records


def _validate_options(options):
    options = options or {}
    queries = options.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("JSearch options must include a non-empty 'queries' list")
    if len(queries) > MAX_QUERIES or any(
        not isinstance(query, str) or not query.strip() for query in queries
    ):
        raise ValueError(f"JSearch supports 1-{MAX_QUERIES} non-empty search queries")

    max_pages = options.get("max_pages", 1)
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError(f"JSearch 'max_pages' must be an integer from 1 to {MAX_PAGES}")
    credits = len(queries) * max_pages
    if credits > MAX_REQUEST_CREDITS:
        raise ValueError(
            f"JSearch configuration would use up to {credits} request credits; "
            f"the per-scrape limit is {MAX_REQUEST_CREDITS}"
        )

    date_posted = options.get("date_posted", "month")
    if not isinstance(date_posted, str) or date_posted not in {
        "all",
        "today",
        "3days",
        "week",
        "month",
    }:
        raise ValueError("JSearch 'date_posted' must be all, today, 3days, week, or month")
    country = options.get("country", "ca")
    if not isinstance(country, str) or len(country) != 2:
        raise ValueError("JSearch 'country' must be a two-letter country code")
    return options, queries, max_pages


def fetch_list(board_url, session=None, options=None):
    _options, queries, max_pages = _validate_options(options)
    api_key = os.environ.get("OPENWEBNINJA_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENWEBNINJA_API_KEY is not set")

    session = session or requests.Session()
    records = []
    seen_ids = set()
    seen_urls = set()
    for query in queries:
        params = {
            "query": query.strip(),
            "country": _options.get("country", "ca").lower(),
            "num_pages": max_pages,
            "date_posted": _options.get("date_posted", "month"),
        }
        for key in (
            "language",
            "work_from_home",
            "employment_types",
            "job_requirements",
            "radius",
            "exclude_job_publishers",
            "fields",
        ):
            if key in _options:
                params[key] = _options[key]

        response = session.get(
            API,
            params=params,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=45,
        )
        response.raise_for_status()
        for record in parse_search_results(response.json()):
            normalized_url = record.url.rstrip("/").casefold()
            if (
                (record.source_job_id and record.source_job_id in seen_ids)
                or normalized_url in seen_urls
            ):
                continue
            if record.source_job_id:
                seen_ids.add(record.source_job_id)
            seen_urls.add(normalized_url)
            records.append(record)
    return records


def fetch_detail(board_url, rec, session=None, options=None):
    return {}
