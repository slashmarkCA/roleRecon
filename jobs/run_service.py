import logging
import time
from collections import Counter
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone

from jobs.models import Employer, EmployerRunResult, Job, ScrapeRun
from rules.filters import evaluate, load_config
from scrapers.registry import get_adapter

logger = logging.getLogger(__name__)

DETAIL_FIELDS = ("description", "location", "work_mode", "employment_type", "salary_text", "posted_at")
TITLE_REASONS = ("excluded employer", "excluded title keyword", "title has no include keyword")
RETRY_DELAYS = (1, 2)
TERMINAL_STATUSES = {
    ScrapeRun.Status.SUCCEEDED,
    ScrapeRun.Status.PARTIAL,
    ScrapeRun.Status.FAILED,
}


def create_run(operation, *, queued=False):
    return ScrapeRun.objects.create(
        operation=operation,
        status=ScrapeRun.Status.QUEUED if queued else ScrapeRun.Status.RUNNING,
        started_at=None if queued else timezone.now(),
    )


def claim_next_run():
    with transaction.atomic():
        run = (
            ScrapeRun.objects.filter(status=ScrapeRun.Status.QUEUED)
            .order_by("created_at")
            .select_for_update(skip_locked=True)
            .first()
        )
        if run is None:
            return None
        run.status = ScrapeRun.Status.RUNNING
        run.started_at = timezone.now()
        run.progress_message = "Starting"
        run.save(update_fields=["status", "started_at", "progress_message", "updated_at"])
        return run


def _exception_summary(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        reason = (exc.response.reason or "").replace("\r", " ").replace("\n", " ")[:100]
        return f"HTTP {exc.response.status_code} {reason}".strip()
    if isinstance(exc, requests.Timeout):
        return "Request timed out"
    if isinstance(exc, requests.ConnectionError):
        return "Connection failed"
    if isinstance(exc, requests.RequestException):
        return type(exc).__name__
    if isinstance(exc, ValueError):
        return str(exc)[:500]
    return f"{type(exc).__name__}; see the local log for details"


def _request_with_retry(callback, description):
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return callback()
        except requests.RequestException as exc:
            response = exc.response
            retryable_status = response is not None and (
                response.status_code == 429 or response.status_code >= 500
            )
            retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or retryable_status
            if not retryable or attempt == len(RETRY_DELAYS):
                raise
            delay = RETRY_DELAYS[attempt]
            logger.warning("%s failed (%s); retrying in %s second(s)", description, type(exc).__name__, delay)
            time.sleep(delay)


def _apply_detail(record, detail):
    for key in DETAIL_FIELDS:
        value = detail.get(key)
        if value:
            setattr(record, key, value)


def _list_limit(adapter, board_url):
    func = getattr(adapter, "list_limit", None)
    return func(board_url) if func else getattr(adapter, "MAX_JOBS", None)


def _save_progress(run, *, current=None, total=None, message=None):
    fields = []
    if current is not None:
        run.progress_current = current
        fields.append("progress_current")
    if total is not None:
        run.progress_total = total
        fields.append("progress_total")
    if message is not None:
        run.progress_message = message[:300]
        fields.append("progress_message")
    if fields:
        run.save(update_fields=[*fields, "updated_at"])


def _process_employer(run, employer, session, config, position, total):
    result_row = EmployerRunResult.objects.create(
        run=run,
        employer=employer,
        employer_name=employer.name,
    )
    _save_progress(run, current=position - 1, total=total, message=f"Fetching {employer.name}")
    logger.info("Scrape run %s: starting employer %s", run.pk, employer.name)
    found = new = kept = filtered = 0

    try:
        adapter = get_adapter(employer.adapter)
        if adapter is None:
            message = f"No scraper is implemented for adapter '{employer.adapter}'"
            result_row.status = EmployerRunResult.Status.SKIPPED
            result_row.summary = message
            result_row.finished_at = timezone.now()
            result_row.save(update_fields=["status", "summary", "finished_at"])
            logger.warning("Scrape run %s: %s: %s", run.pk, employer.name, message)
            return

        records = _request_with_retry(
            lambda: adapter.fetch_list(employer.board_url, session),
            f"{employer.name} job list",
        )
        found = len(records)
        result_row.found = found
        known = set(
            Job.objects.filter(url__in=[record.url for record in records])
            .values_list("url", flat=True)
        )
        detail_error_summaries = []
        reasons = Counter()

        for record_number, record in enumerate(records, start=1):
            if record_number == 1 or record_number % 10 == 0:
                _save_progress(
                    run,
                    message=f"Processing {employer.name}: job {record_number} of {len(records)}",
                )
            if record.url in known:
                Job.objects.filter(url=record.url).update(last_seen=timezone.now())
                continue

            outcome = evaluate(record, employer.name, config)
            if outcome.keep or not outcome.reason.startswith(TITLE_REASONS):
                try:
                    detail = _request_with_retry(
                        lambda: adapter.fetch_detail(employer.board_url, record, session),
                        f"{employer.name} detail for {record.title}",
                    )
                    _apply_detail(record, detail)
                except Exception as exc:
                    detail_error_summaries.append(_exception_summary(exc))
                    logger.exception(
                        "Scrape run %s: detail fetch failed for %s (%s)",
                        run.pk,
                        employer.name,
                        record.title,
                    )
                time.sleep(1)
                outcome = evaluate(record, employer.name, config)

            override = (
                employer.options.get("location_override")
                if isinstance(employer.options, dict)
                else None
            )
            if override:
                record.location = f"{override} ({record.location})" if record.location else override
                outcome = evaluate(record, employer.name, config)

            flags = list(outcome.flags)
            if not record.description:
                flags.append("no description")
            Job.objects.create(
                employer=employer,
                url=record.url,
                source_job_id=record.source_job_id[:200],
                title=record.title[:300],
                company=record.company[:200],
                location=record.location[:200],
                work_mode=record.work_mode[:20],
                employment_type=record.employment_type[:50],
                salary_text=record.salary_text[:200],
                posted_at=record.posted_at,
                description=record.description,
                status=Job.Status.NEW if outcome.keep else Job.Status.FILTERED,
                filter_reason=outcome.reason[:200],
                score=outcome.score,
                flags=flags,
            )
            new += 1
            kept += outcome.keep
            filtered += not outcome.keep
            if not outcome.keep:
                reasons[outcome.reason.split(":")[0]] += 1

        reason_summary = ""
        if filtered:
            reason_summary = ": " + ", ".join(
                f"{count} {reason}" for reason, count in reasons.most_common()
            )
        summary = f"{len(records)} found, {new} new ({kept} kept, {filtered} filtered{reason_summary})"
        warnings = []
        limit = _list_limit(adapter, employer.board_url)
        if limit and len(records) >= limit:
            warnings.append(f"returned its {limit}-job limit; results may be incomplete")
        if not records:
            warnings.append("returned no jobs; confirm the board is still active")
        if detail_error_summaries:
            unique_errors = list(dict.fromkeys(detail_error_summaries))
            warnings.append(
                f"{len(detail_error_summaries)} detail request(s) failed "
                f"({'; '.join(unique_errors[:3])})"
            )
        if warnings:
            summary += " [WARNING: " + "; ".join(warnings) + "]"
            result_row.status = EmployerRunResult.Status.WARNING
            result_row.error_summary = "; ".join(warnings)
            logger.warning("Scrape run %s: %s: %s", run.pk, employer.name, "; ".join(warnings))
        else:
            result_row.status = EmployerRunResult.Status.SUCCEEDED

        result_row.found = len(records)
        result_row.new = new
        result_row.kept = kept
        result_row.filtered = filtered
        result_row.summary = summary
        result_row.finished_at = timezone.now()
        result_row.save()
        if not warnings:
            logger.info("Scrape run %s: %s", run.pk, summary)
    except Exception as exc:
        error = _exception_summary(exc)
        result_row.status = EmployerRunResult.Status.FAILED
        result_row.found = found
        result_row.new = new
        result_row.kept = kept
        result_row.filtered = filtered
        result_row.error_summary = error
        result_row.summary = f"FAILED: {error}"
        result_row.finished_at = timezone.now()
        result_row.save()
        logger.exception("Scrape run %s: employer %s failed", run.pk, employer.name)
    finally:
        _save_progress(run, current=position, total=total, message=f"Finished {employer.name}")


def _run_scrape(run):
    config = load_config()
    employers = list(Employer.objects.filter(active=True).order_by("name"))
    _save_progress(run, current=0, total=len(employers), message="Starting scrape")
    with requests.Session() as session:
        for position, employer in enumerate(employers, start=1):
            _process_employer(run, employer, session, config, position, len(employers))

    results = list(run.employer_results.all())
    failed = sum(result.status == EmployerRunResult.Status.FAILED for result in results)
    warnings = sum(
        result.status in {EmployerRunResult.Status.WARNING, EmployerRunResult.Status.SKIPPED}
        for result in results
    )
    run.summary = (
        f"Scrape finished: {len(results)} employer(s), "
        f"{failed} failed, {warnings} warning(s)."
    )
    run.error_summary = "\n".join(
        f"{result.employer_name}: {result.error_summary}"
        for result in results
        if result.error_summary
    )
    return ScrapeRun.Status.PARTIAL if failed or warnings else ScrapeRun.Status.SUCCEEDED


def _run_refilter(run):
    config = load_config()
    jobs = (
        Job.objects.filter(status__in=[Job.Status.NEW, Job.Status.FILTERED])
        .select_related("employer")
        .order_by("id")
    )
    total = jobs.count()
    changed = kept = 0
    _save_progress(run, current=0, total=total, message="Re-evaluating stored jobs")

    for index, job in enumerate(jobs.iterator(chunk_size=500), start=1):
        outcome = evaluate(job, job.employer.name, config)
        status = Job.Status.NEW if outcome.keep else Job.Status.FILTERED
        kept += outcome.keep
        flags = list(outcome.flags)
        if not job.description:
            flags.append("no description")
        new_values = (status, outcome.reason[:200], outcome.score, flags)
        if new_values != (job.status, job.filter_reason, job.score, job.flags):
            job.status, job.filter_reason, job.score, job.flags = new_values
            job.save(update_fields=["status", "filter_reason", "score", "flags"])
            changed += 1
        if index % 25 == 0 or index == total:
            _save_progress(run, current=index, total=total)

    run.summary = (
        f"{total} jobs checked, {changed} changed, {kept} now kept, {total - kept} filtered"
    )
    return ScrapeRun.Status.SUCCEEDED


def execute_run(run):
    logger.info("Run %s (%s) started", run.pk, run.operation)
    try:
        if run.operation == ScrapeRun.Operation.SCRAPE:
            status = _run_scrape(run)
        elif run.operation == ScrapeRun.Operation.REFILTER:
            status = _run_refilter(run)
        else:
            raise ValueError(f"Unsupported run operation: {run.operation}")
    except Exception as exc:
        run.status = ScrapeRun.Status.FAILED
        run.error_summary = _exception_summary(exc)
        run.summary = f"Run failed: {run.error_summary}"
        logger.exception("Run %s (%s) failed", run.pk, run.operation)
    else:
        run.status = status
    run.finished_at = timezone.now()
    run.progress_message = run.summary[:300]
    run.save(update_fields=[
        "status",
        "summary",
        "error_summary",
        "finished_at",
        "progress_message",
        "updated_at",
    ])
    logger.info("Run %s completed with status %s: %s", run.pk, run.status, run.summary)
    return run


def mark_stale_runs_failed(stale_after=timedelta(minutes=20)):
    cutoff = timezone.now() - stale_after
    stale_runs = ScrapeRun.objects.filter(
        status=ScrapeRun.Status.RUNNING,
        updated_at__lt=cutoff,
    )
    for run in stale_runs:
        run.status = ScrapeRun.Status.FAILED
        run.error_summary = "Worker stopped reporting progress; check the local log."
        run.summary = "Run marked failed because its worker stopped reporting progress."
        run.finished_at = timezone.now()
        run.save(update_fields=[
            "status", "error_summary", "summary", "finished_at", "updated_at",
        ])
        logger.error("Run %s marked failed after stale worker heartbeat", run.pk)


def mark_worker_run_failed_after_database_error(run_id):
    now = timezone.now()
    updated = ScrapeRun.objects.filter(
        pk=run_id,
        status=ScrapeRun.Status.RUNNING,
    ).update(
        status=ScrapeRun.Status.FAILED,
        error_summary="Worker lost its database connection while processing this run.",
        summary="Run marked failed after the worker lost its database connection.",
        progress_message="Run failed after a database connection error.",
        finished_at=now,
        updated_at=now,
    )
    if updated:
        logger.error("Run %s marked failed after a worker database connection error", run_id)
