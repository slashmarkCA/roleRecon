from django.core.management.base import BaseCommand

from jobs.models import Job
from rules.filters import evaluate, load_config


class Command(BaseCommand):
    help = ("Re-run the filters on stored jobs, e.g. after editing search_config.json. "
            "Only touches jobs that are still 'new' or 'filtered'; jobs you saved, "
            "applied to or ignored keep their status. Makes no network requests.")

    def handle(self, *args, **options):
        config = load_config()
        jobs = (Job.objects
                .filter(status__in=[Job.Status.NEW, Job.Status.FILTERED])
                .select_related("employer"))

        checked = changed = kept = 0
        for job in jobs:
            checked += 1
            result = evaluate(job, job.employer.name, config)
            status = Job.Status.NEW if result.keep else Job.Status.FILTERED
            kept += result.keep
            flags = list(result.flags)
            if not job.description:
                flags.append("no description")

            new_values = (status, result.reason[:200], result.score, flags)
            if new_values != (job.status, job.filter_reason, job.score, job.flags):
                job.status, job.filter_reason, job.score, job.flags = new_values
                job.save(update_fields=["status", "filter_reason", "score", "flags"])
                changed += 1

        self.stdout.write(
            f"{checked} jobs checked, {changed} changed, {kept} now kept, {checked - kept} filtered")
