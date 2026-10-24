from scrapers import jobbank

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title type="html"><![CDATA[business analyst]]></title>
    <link rel="alternate" type="text/html" href="https://www.jobbank.gc.ca/jobsearch/jobposting/1000001"/>
    <updated>2026-01-02T12:15:00Z</updated>
    <summary type="html"><![CDATA[<strong>Job number:</strong> 123456<br /><strong>Location:</strong> Toronto (ON)  <br /><strong>Employer:</strong> ACME INC<br /><strong>Salary:</strong> $43.50 hourly]]></summary>
  </entry>
  <entry>
    <title type="html"><![CDATA[entry without a link]]></title>
    <updated>2026-01-02T12:15:00Z</updated>
  </entry>
  <entry>
    <title type="html"><![CDATA[sparse entry]]></title>
    <link rel="alternate" type="text/html" href="https://www.jobbank.gc.ca/jobsearch/jobposting/1000002"/>
  </entry>
</feed>"""


def test_parse_feed_fields():
    job = jobbank.parse_feed(SAMPLE)[0]
    assert job.title == "business analyst"
    assert job.company == "ACME INC"
    assert job.location == "Toronto (ON)"
    assert job.salary_text == "$43.50 hourly"
    assert job.source_job_id == "1000001"
    assert job.url == "https://www.jobbank.gc.ca/jobsearch/jobposting/1000001"
    assert job.posted_at is not None


def test_entries_without_a_link_are_skipped():
    titles = [j.title for j in jobbank.parse_feed(SAMPLE)]
    assert "entry without a link" not in titles
    assert len(titles) == 2


def test_sparse_entry_gets_empty_fields():
    sparse = jobbank.parse_feed(SAMPLE)[1]
    assert sparse.company == "" and sparse.location == "" and sparse.posted_at is None


def test_parse_feed_accepts_bytes():
    assert len(jobbank.parse_feed(SAMPLE.encode("utf-8"))) == 2


def test_list_limit_reads_the_rows_parameter():
    assert jobbank.list_limit("https://example.org/feed?fage=2&rows=100&sort=D") == 100
    assert jobbank.list_limit("https://example.org/feed?rows=25") == 25
    assert jobbank.list_limit("https://example.org/feed?fage=2") is None
