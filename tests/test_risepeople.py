from datetime import datetime, timezone

import pytest

from scrapers import risepeople

BOARD = "https://careers.risepeople.com/example-company/en"


def test_parse_board_url_accepts_board_and_posting_urls():
    expected = {"company_uri": "example-company", "language": "en"}
    assert risepeople.parse_board_url(BOARD) == expected
    assert risepeople.parse_board_url(f"{BOARD}/123_example-role") == expected


def test_parse_board_url_rejects_other_hosts_and_invalid_paths():
    with pytest.raises(ValueError, match="Expected a Rise People"):
        risepeople.parse_board_url("https://example.com/example-company/en")
    with pytest.raises(ValueError, match="Expected a Rise People"):
        risepeople.parse_board_url("https://careers.risepeople.com/example-company")


def test_parse_job_list_extracts_summaries_and_remote_location():
    data = {
        "departments": [
            {
                "title": "Technology",
                "positions": [
                    {
                        "id": 123,
                        "title": "Data Engineer",
                        "city": "Toronto",
                        "province": "ON",
                        "country": "Canada",
                        "remote_position": True,
                        "job_type": ["Full-time"],
                    },
                    {
                        "id": 456,
                        "title": "Business Analyst",
                        "city": "Toronto",
                        "province": "ON",
                        "country": "Canada",
                        "remote_position": False,
                        "job_type": ["Part-time", "Contract"],
                    },
                    {
                        "id": 789,
                        "title": "Project Manager",
                        "city": "Moncton",
                        "province": "",
                        "country": "Canada",
                        "remote_position": False,
                        "job_type": [],
                    },
                ],
            },
        ],
    }

    first, second, third = risepeople.parse_job_list(data, f"{BOARD}/123_old-role")

    assert first.source_job_id == "123"
    assert first.url == f"{BOARD}/123_data-engineer"
    assert first.title == "Data Engineer"
    assert first.location == "Toronto, ON or Remote"
    assert first.work_mode == "Remote"
    assert first.employment_type == "Full-time"
    assert second.location == "Toronto, ON"
    assert second.employment_type == "Part-time, Contract"
    assert third.location == "Moncton, Canada"


def test_parse_job_list_rejects_missing_or_malformed_data():
    with pytest.raises(ValueError, match="missing its departments"):
        risepeople.parse_job_list({}, BOARD)
    with pytest.raises(ValueError, match="invalid department"):
        risepeople.parse_job_list({"departments": [{}]}, BOARD)


def test_parse_job_detail_extracts_description_and_posting_fields():
    data = {
        "opened": "2026-05-15T12:30:00Z",
        "descriptions": [
            {
                "language": "en",
                "title": "Data Engineer",
                "city": "Toronto",
                "province": "ON",
                "country": "Canada",
                "remote_position": True,
                "job_type": ["Full-time"],
                "description": "<p>Build reliable data pipelines.</p><ul><li>Own quality.</li></ul>",
            },
        ],
    }

    detail = risepeople.parse_job_detail(data, BOARD)

    assert detail["description"] == "Build reliable data pipelines.\nOwn quality."
    assert detail["location"] == "Toronto, ON or Remote"
    assert detail["work_mode"] == "Remote"
    assert detail["employment_type"] == "Full-time"
    assert detail["posted_at"] == datetime(2026, 5, 15, 12, 30, tzinfo=timezone.utc)


def test_parse_job_detail_uses_matching_language_and_rejects_empty_description():
    data = {
        "descriptions": [
            {"language": "fr", "description": "<p>Poste en français.</p>"},
            {"language": "en", "description": "<p>English position.</p>"},
        ],
    }
    assert risepeople.parse_job_detail(data, BOARD)["description"] == "English position."

    with pytest.raises(ValueError, match="empty description"):
        risepeople.parse_job_detail({"descriptions": [{"language": "en"}]}, BOARD)
