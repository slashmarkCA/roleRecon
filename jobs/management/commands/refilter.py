from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from jobs.models import ScrapeRun
from jobs.run_service import create_run, execute_run


class Command(BaseCommand):
    help = "Re-apply search_config.json to stored jobs without making network requests"

    def handle(self, *args, **options):
        try:
            run = create_run(ScrapeRun.Operation.REFILTER)
        except IntegrityError as exc:
            raise CommandError("A scrape or refilter is already queued or running.") from exc

        execute_run(run)
        self.stdout.write(run.summary)
        if run.error_summary:
            self.stderr.write(run.error_summary)
        if run.status == ScrapeRun.Status.FAILED:
            raise CommandError(run.summary)
