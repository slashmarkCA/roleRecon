from django.db import models
from django.utils import timezone


class Employer(models.Model):
    class Adapter(models.TextChoices):
        ULTIPRO = "ultipro", "UltiPro / UKG"
        WORKDAY = "workday", "Workday"
        BAMBOOHR = "bamboohr", "BambooHR"
        ORACLE_HCM = "oracle_hcm", "Oracle Recruiting Cloud"
        JOBBANK = "jobbank", "Job Bank (Atom feed)"
        ERECRUIT = "erecruit", "Virtuo HR eRecruit (RSS feed)"
        GREENHOUSE = "greenhouse", "Greenhouse"
        SUCCESSFACTORS = "successfactors", "SuccessFactors"
        PHENOM = "phenom", "Phenom"
        WORKABLE = "workable", "Workable"
        LEVER = "lever", "Lever"
        HTML = "html", "Plain HTML page"
        BROWSER = "browser", "Browser-rendered page"
        LINKEDIN = "linkedin", "LinkedIn search"

    name = models.CharField(max_length=200, unique=True)
    adapter = models.CharField(max_length=20, choices=Adapter.choices)
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