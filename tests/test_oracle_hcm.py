from scrapers import oracle_hcm

BOARD = "https://example.fa.ca2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs?mode=location"

LIST = {"items": [{
    "TotalJobsCount": 2,
    "requisitionList": [
        {"Id": "1001", "Title": "QA Analyst", "PostedDate": "2026-01-02",
         "PrimaryLocation": "Canada", "WorkplaceType": "On-site"},
        {"Id": "1002", "Title": "Business Analyst", "PrimaryLocation": "Toronto"},
    ],
}]}

DETAIL = {"items": [{
    "ExternalDescriptionStr": "<p>Hello <b>world</b></p>",
    "workLocation": [{"LocationName": "Head Office"}, {"LocationName": "Annex"}],
    "JobSchedule": "Full Time",
    "requisitionFlexFields": [
        {"Prompt": "Is this a Contract Position?", "Value": "Yes"},
        {"Prompt": "Minimum Pay Range", "Value": "$50,000"},
        {"Prompt": "Maximum Pay Range", "Value": "$70,000"},
    ],
    "ExternalPostedStartDate": "2026-01-02T03:04:05+00:00",
}]}


def test_parse_board_url():
    b = oracle_hcm.parse_board_url(BOARD)
    assert b["host"] == "example.fa.ca2.oraclecloud.com" and b["site"] == "CX_1"
    assert b["api_base"] == "https://example.fa.ca2.oraclecloud.com/hcmRestApi/resources/latest"


def test_list_url_has_the_finder_parts():
    url = oracle_hcm._list_url(BOARD, offset=50)
    assert "finder=findReqs;siteNumber=CX_1,limit=50,offset=50" in url


def test_parse_list():
    jobs, total = oracle_hcm.parse_list(LIST, BOARD)
    assert total == 2 and [j.title for j in jobs] == ["QA Analyst", "Business Analyst"]
    first = jobs[0]
    assert first.location == "Canada" and first.work_mode == "On-site"
    assert first.posted_at is not None
    assert first.url == "https://example.fa.ca2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/1001"
    assert jobs[1].work_mode == "" and jobs[1].posted_at is None


def test_parse_detail():
    detail = oracle_hcm.parse_detail(DETAIL)
    assert "Hello" in detail["description"] and "<" not in detail["description"]
    assert detail["location"] == "Head Office; Annex"
    assert detail["employment_type"] == "Full Time Contract"
    assert detail["salary_text"] == "$50,000 - $70,000"
    assert detail["posted_at"] is not None
