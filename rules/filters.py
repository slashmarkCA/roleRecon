import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "search_config.json"


def _dedupe(items):
    """Remove duplicates from a list, case-insensitively, keeping first-seen order."""
    seen, out = set(), []
    for item in items:
        key = item.strip().lower() if isinstance(item, str) else item
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def load_config(path=DEFAULT_PATH):
    """Load the JSON config, dropping keys that start with '_' and de-duplicating lists."""
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if not k.startswith("_")}
        if isinstance(x, list):
            return _dedupe([clean(i) for i in x])
        return x

    return clean(json.loads(Path(path).read_text(encoding="utf-8")))


def _find(term, text, whole_words=True):
    if not term:
        return False
    if whole_words:
        return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) is not None
    return term.lower() in text.lower()


def classify_arrangement(text):
    t = text.lower()
    if "hybrid" in t:
        return "hybrid"
    if "remote" in t:
        return "remote"
    if re.search(r"on-?site|in-?office|in-?person", t):
        return "onsite"
    return None


@dataclass
class Result:
    keep: bool
    reason: str = ""
    score: int = 0
    flags: list = field(default_factory=list)


def evaluate(job, employer_name, config):
    """Decide whether to keep a job. `job` needs: title, description, location,
    work_mode, employment_type. Returns a Result."""
    f = config.get("filters", {})
    ww = config.get("titleMatch", {}).get("wholeWords", True)
    title, desc = job.title or "", job.description or ""
    flags = []
    # Sources that list many employers (Job Bank) set job.company; otherwise use the employer row.
    employer_name = getattr(job, "company", "") or employer_name

    for term in f.get("excludedEmployers", []):
        if _find(term, employer_name, whole_words=False):
            return Result(False, f"excluded employer: {term}")

    for term in f.get("excludedTitleKeywords", []):
        if _find(term, title, ww):
            return Result(False, f"excluded title keyword: {term}")

    include = config.get("titleMatch", {}).get("includeKeywords", [])
    if include and not any(_find(k, title, ww) for k in include):
        return Result(False, "title has no include keyword")

    accept = config.get("locations", {}).get("accept", [])
    if accept:
        place = f"{job.location or ''} {job.work_mode or ''}".strip()
        if not place:
            flags.append("location unclear")
        elif not any(_find(a, place, True) for a in accept):
            return Result(False, f"location not accepted: {job.location or job.work_mode}")

    for term in f.get("excludedEmploymentTypes", []):
        if _find(term, job.employment_type or "", whole_words=False):
            return Result(False, f"excluded employment type: {term}")

    for group, terms in f.get("descriptionExclusions", {}).items():
        for term in terms:
            if _find(term, desc, ww):
                return Result(False, f"description exclusion ({group}): {term}")

    mode = classify_arrangement(f"{job.work_mode} {job.location}") or classify_arrangement(desc)
    if mode is None:
        flags.append("arrangement unclear")
    else:
        key = {"remote": "acceptRemote", "hybrid": "acceptHybrid", "onsite": "acceptOnsite"}[mode]
        if config.get("workArrangement", {}).get(key, True) is False:
            return Result(False, f"work arrangement not accepted: {mode}")

    text = f"{title} {desc}"
    score = sum(1 for k in f.get("preferredKeywords", []) if _find(k, text, ww))
    return Result(True, score=score, flags=flags)
