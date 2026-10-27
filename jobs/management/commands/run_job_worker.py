import logging
import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections
from django.utils import timezone

from jobs.models import ScrapeRun
from jobs.run_service import (
    claim_next_run,
    execute_run,
    mark_stale_runs_failed,
    mark_worker_run_failed_after_database_error,
)

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
        interrupted_run_id = None
        database_retry_seconds = 1
        self.stdout.write("Worker started; waiting for queued runs. Press Ctrl+C to stop.")
        logger.info("Run worker started; polling every %.1f seconds", poll_seconds)
        try:
            while True:
                try:
                    close_old_connections()
                    if interrupted_run_id is not None:
                        mark_worker_run_failed_after_database_error(interrupted_run_id)
                        interrupted_run_id = None
                    mark_stale_runs_failed()
                    run = claim_next_run()
                    if run is not None:
                        execute_run(run)
                        run = None
                    elif options["once"]:
                        return
                except OperationalError:
                    if run is not None:
                        interrupted_run_id = run.pk
                        run = None
                    logger.exception(
                        "Database unavailable in run worker; retrying in %s second(s)",
                        database_retry_seconds,
                    )
                    time.sleep(database_retry_seconds)
                    database_retry_seconds = min(database_retry_seconds * 2, 30)
                    continue
                database_retry_seconds = 1
                if run is None:
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
            if interrupted_run_id is not None:
                try:
                    mark_worker_run_failed_after_database_error(interrupted_run_id)
                except OperationalError:
                    logger.exception(
                        "Could not mark run %s failed before worker shutdown",
                        interrupted_run_id,
                    )
            self.stdout.write("Worker stopped.")
