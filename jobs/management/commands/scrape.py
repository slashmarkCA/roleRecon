import time
from collections import Counter

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Employer, Job
from rules.filters import evaluate, load_config
from scrapers import (
    bamboohr, erecruit, greenhouse, jobbank, oracle_hcm, phenom, successfactors, ultipro,
    workable, workday,
)

ADAPTERS = {
    "ultipro": ultipro,
    "workday": workday,
    "greenhouse": greenhouse,
    "bamboohr": bamboohr,
    "oracle_hcm": oracle_hcm,
    "jobbank": jobbank,
    "erecruit": erecruit,
    "successfactors": successfactors,
    "phenom": phenom,
    "workable": workable,
}

DETAIL_FIELDS = ("description", "location", "work_mode", "employment_type", "salary_text", "posted_at")
TITLE_REASONS = ("excluded employer", "excluded title keyword", "title has no include keyword")


def list_limit(adapter, board_url):
    """The most jobs this source can return in one scrape (None if unknown)."""
    func = getattr(adapter, "list_limit", None)
    return func(board_url) if func else getattr(adapter, "MAX_JOBS", None)


def apply_detail(rec, detail):
    """Copy any non-empty values from the adapter's detail fetch onto the job record."""
    for key in DETAIL_FIELDS:
        value = detail.get(key)
        if value:
            setattr(rec, key, value)


class Command(BaseCommand):
    help = "Fetch jobs from every active employer, filter them, and store the new ones"

    def handle(self, *args, **options):
        try:
            config = load_config()
        except FileNotFoundError:
            self.stderr.write("search_config.json not found in the project root; copy "
                              "search_config.example.json to search_config.json first.")
            return

        session = requests.Session()
        for emp in Employer.objects.filter(active=True):
            adapter = ADAPTERS.get(emp.adapter)
            if adapter is None:
                self.stdout.write(f"{emp.name}: no adapter for '{emp.adapter}', skipped")
                continue
            try:
                records = adapter.fetch_list(emp.board_url, session)
            except Exception as e:
                self.stderr.write(f"{emp.name}: FAILED ({e})")
                continue

            known = set(Job.objects.filter(url__in=[r.url for r in records])
                        .values_list("url", flat=True))
            new = kept = filtered = 0
            reasons = Counter()  # why filtered jobs were rejected, for the summary line
            for rec in records:
                if rec.url in known:
                    Job.objects.filter(url=rec.url).update(last_seen=timezone.now())
                    continue

                # A rejection based on the title (or employer) is final, so skip the
                # slow detail request for those; big employers have many irrelevant jobs.
                result = evaluate(rec, emp.name, config)
                if result.keep or not result.reason.startswith(TITLE_REASONS):
                    try:
                        apply_detail(rec, adapter.fetch_detail(emp.board_url, rec, session))
                    except Exception as e:
                        self.stderr.write(f"  detail failed for {rec.title}: {e}")
                    time.sleep(1)
                    result = evaluate(rec, emp.name, config)
                # Optional per-employer setting, e.g. when an Oracle site lists every job as "Canada":
                # Employer.options = {"location_override": "Toronto"}
                override = emp.options.get("location_override") if isinstance(emp.options, dict) else None
                if override:
                    rec.location = f"{override} ({rec.location})" if rec.location else override
                    result = evaluate(rec, emp.name, config)
                flags = list(result.flags)
                if not rec.description:
                    flags.append("no description")
                Job.objects.create(
                    employer=emp,
                    url=rec.url,
                    source_job_id=rec.source_job_id[:200],
                    title=rec.title[:300],
                    company=rec.company[:200],
                    location=rec.location[:200],
                    work_mode=rec.work_mode[:20],
                    employment_type=rec.employment_type[:50],
                    salary_text=rec.salary_text[:200],
                    posted_at=rec.posted_at,
                    description=rec.description,
                    status=Job.Status.NEW if result.keep else Job.Status.FILTERED,
                    filter_reason=result.reason[:200],
                    score=result.score,
                    flags=flags,
                )
                new += 1
                kept += result.keep
                filtered += not result.keep
                if not result.keep:
                    reasons[result.reason.split(":")[0]] += 1

            breakdown = ""
            if filtered:
                breakdown = ": " + ", ".join(f"{n} {why}" for why, n in reasons.most_common())
            self.stdout.write(
                f"{emp.name}: {len(records)} found, {new} new "
                f"({kept} kept, {filtered} filtered{breakdown})")
            limit = list_limit(adapter, emp.board_url)
            if limit and len(records) >= limit:
                self.stdout.write(self.style.WARNING(
                    f"  WARNING: {emp.name} returned {len(records)} jobs, the most this source "
                    f"returns; the list may be cut off."))
