from scrapers.jsearch_pilot import parse_report_jobs, parse_report_queries


REPORT = """\
# Pilot

| Search | Returned | Passed filters |
|---|---:|---:|
| Analyst jobs in Toronto | 10 | 4 |
| QA jobs in Ajax | 5 | 2 |

## Jobs passing current filters

### 1. Business Analyst

- Company: Example Bank
- Location: Toronto, ON
- Publisher: LinkedIn
- Posted: 2026-10-30T12:00:00.000Z
- Employment type: FULLTIME
- Salary: Not supplied
- roleRecon score: 3
- Apply/source link: https://jobs.example.test/1

<details>
<summary>Job description</summary>

<pre>
Build &amp; improve useful systems.
</pre>
</details>
"""


def test_report_parser_extracts_saved_queries_and_job_description():
    assert parse_report_queries(REPORT) == [
        "Analyst jobs in Toronto",
        "QA jobs in Ajax",
    ]
    job = parse_report_jobs(REPORT)[0]
    assert job["title"] == "Business Analyst"
    assert job["company"] == "Example Bank"
    assert job["url"] == "https://jobs.example.test/1"
    assert job["description"] == "Build & improve useful systems."
