from datetime import timezone

from scrapers import bamboohr

BOARD = "https://example.bamboohr.com/careers"

LIST = {
    "result": [
        {
            "id": "7",
            "jobOpeningName": "QA Analyst",
            "employmentStatusLabel": "Full-Time",
            "location": {"city": "Toronto", "state": "Ontario"},
            "isRemote": False,
        },
        {
            "id": 8,
            "jobOpeningName": "Remote Analyst",
            "isRemote": True,
            "atsLocation": {"city": None, "province": "Ontario"},
        },
    ]
}


def test_parse_list():
    first, second = bamboohr.parse_list(LIST, BOARD)
    assert first.title == "QA Analyst" and first.source_job_id == "7"
    assert first.url == "https://example.bamboohr.com/careers/7"
    assert first.location == "Toronto, Ontario"
    assert first.employment_type == "Full-Time" and first.work_mode == ""
    assert second.work_mode == "Remote"
    assert second.location == "Ontario"  # falls back to atsLocation, skipping the empty city


def test_parse_detail():
    data = {"result": {"jobOpening": {
        "description": "<p>Hello <b>world</b></p>",
        "datePosted": "2026-01-02",
        "location": {"city": "Toronto", "state": "Ontario"},
    }}}
    detail = bamboohr.parse_detail(data)
    assert "Hello" in detail["description"] and "<" not in detail["description"]
    assert detail["location"] == "Toronto, Ontario"
    assert detail["posted_at"].tzinfo == timezone.utc


def test_parse_detail_tolerates_missing_fields():
    detail = bamboohr.parse_detail({"result": {}})
    assert detail["description"] == "" and detail["posted_at"] is None
