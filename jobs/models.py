from django.db import models
from django.utils import timezone

from scrapers.registry import ADAPTER_CHOICES


class Employer(models.Model):
    name = models.CharField(max_length=200, unique=True)
    adapter = models.CharField(max_length=20, choices=ADAPTER_CHOICES)
    board_url = models.URLField(max_length=500)
    options = models.JSONField(default=dict, blank=True)  # selectors, API params
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Job(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        SAVED = "saved", "Saved"
        APPLIED = "applied", "Applied"
        IGNORED = "ignored", "Ignored"
        FILTERED = "filtered", "Filtered out"

    employer = models.ForeignKey(Employer, on_delete=models.CASCADE, related_name="jobs")
    source_job_id = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=1000, unique=True)
    title = models.CharField(max_length=300)
    company = models.CharField(max_length=200, blank=True)  # set when a source lists many employers
    location = models.CharField(max_length=200, blank=True)
    work_mode = models.CharField(max_length=20, blank=True)
    employment_type = models.CharField(max_length=50, blank=True)
    salary_text = models.CharField(max_length=200, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    filter_reason = models.CharField(max_length=200, blank=True)
    score = models.IntegerField(default=0)  # count of preferred keywords matched
    flags = models.JSONField(default=list, blank=True)  # e.g. ["arrangement unclear"]
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-first_seen"]

    def __str__(self):
        return f"{self.title} ({self.employer})"


class ScrapeRun(models.Model):
    class Operation(models.TextChoices):
        SCRAPE = "scrape", "Scrape"
        REFILTER = "refilter", "Refilter"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        PARTIAL = "partial", "Completed with errors"
        FAILED = "failed", "Failed"

    operation = models.CharField(max_length=20, choices=Operation.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    progress_message = models.CharField(max_length=300, blank=True)
    summary = models.TextField(blank=True)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(status__in=["queued", "running"]),
                name="one_active_scrape_run",
            ),
        ]

    def __str__(self):
        return f"{self.get_operation_display()} {self.get_status_display()} ({self.pk})"


class EmployerRunResult(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        WARNING = "warning", "Warning"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    run = models.ForeignKey(ScrapeRun, on_delete=models.CASCADE, related_name="employer_results")
    employer = models.ForeignKey(
        Employer, on_delete=models.SET_NULL, null=True, blank=True, related_name="run_results"
    )
    employer_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    found = models.PositiveIntegerField(default=0)
    new = models.PositiveIntegerField(default=0)
    kept = models.PositiveIntegerField(default=0)
    filtered = models.PositiveIntegerField(default=0)
    summary = models.TextField(blank=True)
    error_summary = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.employer_name}: {self.get_status_display()}"