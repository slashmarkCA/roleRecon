import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from jobs.models import Employer, Job
from rules.filters import evaluate, load_config
from scrapers.base import JobRecord
from scrapers.jsearch_pilot import parse_posted, parse_report_jobs, parse_report_queries

DEFAULT_REPORT = Path("data/jsearch-pilot-2026-10-30.md")
BOARD_URL = "https://api.openwebninja.com/jsearch/search-v2"
EMPLOYER_NAME = "JSearch Canada"


class Command(BaseCommand):
    help = "Import saved JSearch pilot results into the database without API requests"

    def add_arguments(self, parser):
        parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        report_path = options["report"]
        try:
            markdown = report_path.read_text(encoding="utf-8")
            pilot_jobs = parse_report_jobs(markdown)
            queries = parse_report_queries(markdown)
        except (OSError, ValueError) as exc:
            raise CommandError(f"Could not read the JSearch pilot report: {exc}") from exc
        if not queries:
            raise CommandError("The report does not include any successful search queries")

        employer = Employer.objects.filter(name=EMPLOYER_NAME).first()
        if employer and employer.adapter != "jsearch":
            raise CommandError(
                f"Employer '{EMPLOYER_NAME}' already exists with adapter '{employer.adapter}'"
            )
        if not employer and not options["dry_run"]:
            employer = Employer.objects.create(
                name=EMPLOYER_NAME,
                adapter="jsearch",
                board_url=BOARD_URL,
                options={
                    "queries": queries,
                    "country": "ca",
                    "date_posted": "month",
                    "max_pages": 1,
                },
                active=False,
                notes=(
                    "OpenWeb Ninja JSearch aggregator. Requires OPENWEBNINJA_API_KEY. "
                    "Each query costs up to max_pages request credits; kept inactive after "
                    "the pilot import to avoid unexpected API usage."
                ),
            )

        config = load_config()
        existing_urls = {
            value.rstrip("/").casefold()
            for value in Job.objects.values_list("url", flat=True)
        }
        seen_urls = set()
        created = skipped_existing = filtered = 0
        for item in pilot_jobs:
            normalized_url = item["url"].rstrip("/").casefold()
            if normalized_url in existing_urls or normalized_url in seen_urls:
                skipped_existing += 1
                continue
            seen_urls.add(normalized_url)

            record = JobRecord(
                source_job_id="pilot-" + hashlib.sha256(item["url"].encode()).hexdigest()[:32],
                url=item["url"],
                title=item["title"],
                company=item["company"] if item["company"] != "Not supplied" else "",
                location=item["location"] if item["location"] != "Not supplied" else "",
                employment_type=(
                    item["employment"] if item["employment"] != "Not supplied" else ""
                ),
                salary_text=item["salary"] if item["salary"] != "Not supplied" else "",
                posted_at=parse_posted(item["posted"]),
                description=item["description"],
            )
            outcome = evaluate(record, EMPLOYER_NAME, config)
            if not outcome.keep:
                filtered += 1
            if options["dry_run"]:
                created += 1
                continue

            flags = list(outcome.flags)
            if not record.description:
                flags.append("no description")
            Job.objects.create(
                employer=employer,
                url=record.url,
                source_job_id=record.source_job_id,
                title=record.title[:300],
                company=record.company[:200],
                location=record.location[:200],
                employment_type=record.employment_type[:50],
                salary_text=record.salary_text[:200],
                posted_at=record.posted_at,
                description=record.description,
                status=Job.Status.NEW if outcome.keep else Job.Status.FILTERED,
                filter_reason=outcome.reason[:200],
                score=outcome.score,
                flags=flags,
            )
            created += 1

        mode = "Dry run; no rows written" if options["dry_run"] else "Imported"
        self.stdout.write(
            f"{mode}: {created} jobs; {skipped_existing} already in database; "
            f"{filtered} no longer pass current filters; {len(queries)} saved queries. "
            "No JSearch API calls were made."
        )
