from datetime import datetime, timezone

import pytest

from scrapers import pulsecraft

BOARD = "https://www.pulsecrafttechnologies.com/careers#openings"

LISTING = """
<main>
  <div class="rounded-2xl">
    <span>Engineering</span><span>Full-time</span>
    <h3>Lead Mobile Engineer</h3>
    <span>Oshawa, ON (Hybrid / Remote in Canada)</span>
    <span>5+ Years Experience</span>
    <a href="/careers/lead-mobile-engineer">View &amp; Apply</a>
  </div>
  <div class="rounded-2xl">
    <span>AI Research</span><span>Contract</span>
    <h3>AI Solutions Architect</h3>
    <span>Toronto, ON (Remote)</span>
    <a href="/careers/ai-solutions-architect">View &amp; Apply</a>
  </div>
  <div class="rounded-2xl">
    <h3>External posting</h3>
    <a href="https://example.com/careers/fake">View &amp; Apply</a>
  </div>
</main>
"""

DETAIL = """
<main>
  <section>
    <h1>Lead Mobile Engineer</h1>
    <p>Engineering</p><p>Full-time</p>
    <p>Oshawa, ON (Hybrid / Remote in Canada)</p>
    <p>Posted</p><p>2026-08-15</p>
  </section>
  <section>
    <h2>Role Overview</h2>
    <p>Build mobile applications.</p>
    <h2>Core Responsibilities</h2>
    <ul><li>Lead a team.</li><li>Ship releases.</li></ul>
    <h2>Submit Your Application</h2>
    <form><label>Resume / CV</label></form>
  </section>
</main>
"""


def test_parse_board_url_accepts_the_careers_page_and_fragment():
    assert pulsecraft.parse_board_url(BOARD) == "https://www.pulsecrafttechnologies.com/careers"


def test_parse_board_url_rejects_other_hosts_and_paths():
    with pytest.raises(ValueError, match="PulseCraft careers URL"):
        pulsecraft.parse_board_url("https://example.com/careers")


def test_parse_job_list_extracts_public_cards_and_skips_unrelated_links():
    first, second = pulsecraft.parse_job_list(LISTING, BOARD)

    assert first.source_job_id == "lead-mobile-engineer"
    assert first.url == "https://www.pulsecrafttechnologies.com/careers/lead-mobile-engineer"
    assert first.title == "Lead Mobile Engineer"
    assert first.location == "Oshawa, ON"
    assert first.work_mode == "Hybrid"
    assert first.employment_type == "Full-time"
    assert second.location == "Toronto, ON"
    assert second.work_mode == "Remote"
    assert second.employment_type == "Contract"


def test_parse_job_list_fails_explicitly_when_expected_cards_are_missing():
    with pytest.raises(ValueError, match="missing the expected public job cards"):
        pulsecraft.parse_job_list("<main><h1>Careers</h1></main>", BOARD)


def test_parse_job_detail_extracts_description_and_posted_date_without_form():
    detail = pulsecraft.parse_job_detail(DETAIL)
    assert detail == {
        "title": "Lead Mobile Engineer",
        "description": (
            "Build mobile applications.\n"
            "Core Responsibilities\n"
            "Lead a team.\n"
            "Ship releases."
        ),
        "posted_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
    }


def test_parse_job_detail_rejects_missing_description_sections():
    with pytest.raises(ValueError, match="missing its description sections"):
        pulsecraft.parse_job_detail("<main><h1>Role</h1><p>No role content</p></main>")
