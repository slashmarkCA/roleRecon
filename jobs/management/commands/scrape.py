from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from jobs.models import ScrapeRun
from jobs.run_service import create_run, execute_run


class Command(BaseCommand):
    help = "Fetch jobs from active employers, filter them, and store new jobs"

    def handle(self, *args, **options):
        try:
            run = create_run(ScrapeRun.Operation.SCRAPE)
        except IntegrityError as exc:
            raise CommandError("A scrape or refilter is already queued or running.") from exc

        execute_run(run)
        self.stdout.write(run.summary)
        if run.error_summary:
            self.stderr.write(run.error_summary)
        if run.status in {ScrapeRun.Status.PARTIAL, ScrapeRun.Status.FAILED}:
            raise CommandError(run.summary)
