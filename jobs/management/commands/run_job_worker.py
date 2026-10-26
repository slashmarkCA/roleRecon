import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from jobs.models import ScrapeRun
from jobs.run_service import claim_next_run, execute_run, mark_stale_runs_failed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process queued scrape and refilter runs; keep this command running locally"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one queued run, then exit.",
        )
        parser.add_argument(
            "--poll-seconds",
            type=float,
            default=2,
            help="Seconds to wait between checking the database queue (default: 2).",
        )

    def handle(self, *args, **options):
        poll_seconds = max(0.2, options["poll_seconds"])
        run = None
        self.stdout.write("Worker started; waiting for queued runs. Press Ctrl+C to stop.")
        logger.info("Run worker started; polling every %.1f seconds", poll_seconds)
        try:
            while True:
                close_old_connections()
                mark_stale_runs_failed()
                run = claim_next_run()
                if run is not None:
                    execute_run(run)
                    run = None
                elif options["once"]:
                    return
                else:
                    time.sleep(poll_seconds)
        except KeyboardInterrupt:
            if run is not None and run.status == ScrapeRun.Status.RUNNING:
                run.status = ScrapeRun.Status.FAILED
                run.error_summary = "Worker stopped before the run completed."
                run.summary = "Run interrupted because the local worker was stopped."
                run.finished_at = timezone.now()
                run.save(update_fields=[
                    "status", "error_summary", "summary", "finished_at", "updated_at",
                ])
                logger.warning("Run %s marked failed after worker interruption", run.pk)
            self.stdout.write("Worker stopped.")
