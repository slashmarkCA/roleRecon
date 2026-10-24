import json
from types import SimpleNamespace as NS

from rules.filters import evaluate, load_config

CFG = {
    "titleMatch": {"includeKeywords": ["analyst", "qa"], "wholeWords": True},
    "locations": {"accept": ["Toronto", "Ottawa", "Remote"]},
    "filters": {
        "excludedEmployers": ["acme staffing"],
        "excludedTitleKeywords": ["intern", "quality control"],
        "excludedEmploymentTypes": [],
        "descriptionExclusions": {
            "languageRequirements": ["french"],
            "technicalRequirements": ["java"],
            "platformExclusions": ["salesforce"],
        },
        "preferredKeywords": ["sql", "agile"],
    },
    "workArrangement": {"acceptRemote": True, "acceptHybrid": True, "acceptOnsite": False},
}


def job(title="QA Analyst", desc="", location="Toronto, ON", work_mode="", employment_type=""):
    return NS(title=title, description=desc, location=location,
              work_mode=work_mode, employment_type=employment_type)


def test_keeps_good_job_and_scores_preferred_keywords():
    r = evaluate(job(desc="Hybrid role. Uses SQL and Agile."), "Acme", CFG)
    assert r.keep and r.score == 2 and r.flags == []


def test_excluded_employer():
    assert not evaluate(job(desc="Remote"), "Acme Staffing Inc", CFG).keep


def test_intern_excluded_but_internal_is_not():
    assert not evaluate(job(title="QA Analyst Intern", desc="Remote"), "X", CFG).keep
    assert evaluate(job(title="Internal Tools QA Analyst", desc="Remote"), "X", CFG).keep


def test_title_needs_include_keyword():
    assert not evaluate(job(title="Director of Finance", desc="Remote"), "X", CFG).keep


def test_java_blocks_but_javascript_does_not():
    assert not evaluate(job(desc="Java developer experience. Remote"), "X", CFG).keep
    assert evaluate(job(desc="Strong JavaScript skills. Remote"), "X", CFG).keep


def test_language_and_platform_exclusions():
    assert not evaluate(job(desc="Fluent French required. Remote"), "X", CFG).keep
    assert not evaluate(job(desc="Salesforce admin. Remote"), "X", CFG).keep


def test_onsite_not_accepted():
    assert not evaluate(job(work_mode="On-site"), "X", CFG).keep


def test_unclear_arrangement_is_kept_and_flagged():
    r = evaluate(job(desc="Great team."), "X", CFG)
    assert r.keep and r.flags == ["arrangement unclear"]


# --- location rule (employer boards list every office, so locations must be filtered) ---

def test_winnipeg_is_rejected_and_toronto_kept():
    r = evaluate(job(location="Winnipeg", desc="Hybrid role."), "Acme", CFG)
    assert not r.keep and r.reason.startswith("location not accepted")
    assert evaluate(job(location="Toronto", desc="Hybrid role."), "Acme", CFG).keep


def test_remote_in_accept_list_matches_work_mode():
    r = evaluate(job(location="Winnipeg", work_mode="Remote"), "X", CFG)
    assert r.keep


def test_blank_location_is_kept_and_flagged():
    r = evaluate(job(location="", desc="Remote work."), "X", CFG)
    assert r.keep and r.flags == ["location unclear"]


def test_empty_accept_list_accepts_any_location():
    cfg = {**CFG, "locations": {"accept": []}}
    assert evaluate(job(location="Winnipeg", desc="Hybrid role."), "X", cfg).keep


def test_company_overrides_employer_name_for_multi_employer_sources():
    j = job(desc="Remote")
    j.company = "Acme Staffing Inc"  # e.g. a Job Bank posting
    assert not evaluate(j, "Job Bank", CFG).keep


# --- config loading ---

def test_load_config_ignores_comment_keys_and_dedupes(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({
        "_comment": "ignore me",
        "filters": {"excludedTitleKeywords": ["Intern", "intern", "co-op"]},
    }), encoding="utf-8")
    cfg = load_config(p)
    assert "_comment" not in cfg
    assert cfg["filters"]["excludedTitleKeywords"] == ["Intern", "co-op"]
