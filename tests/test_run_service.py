import json
import os
from types import SimpleNamespace

import django
import pytest
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth.models import AnonymousUser
from django.db import OperationalError, ProgrammingError
from django.test import RequestFactory

from jobs import views
from jobs.management.commands import run_job_worker
from jobs.run_service import _exception_summary, _request_with_retry


def test_exception_summary_does_not_expose_request_url():
    error = requests.Timeout("https://example.test/jobs?token=private")
    assert _exception_summary(error) == "Request timed out"


def test_request_with_retry_retries_connection_errors(monkeypatch):
    attempts = []
    delays = []

    def request():
        attempts.append(None)
        if len(attempts) < 3:
            raise requests.ConnectionError("temporary")
        return "ok"

    monkeypatch.setattr("jobs.run_service.time.sleep", delays.append)

    assert _request_with_retry(request, "example list") == "ok"
    assert len(attempts) == 3
    assert delays == [1, 2]


def test_request_with_retry_does_not_retry_client_errors(monkeypatch):
    attempts = []
    response = requests.Response()
    response.status_code = 404
    error = requests.HTTPError(response=response)
    monkeypatch.setattr("jobs.run_service.time.sleep", lambda _seconds: pytest.fail("unexpected retry"))

    def request():
        attempts.append(None)
        raise error

    with pytest.raises(requests.HTTPError):
        _request_with_retry(request, "example list")
    assert len(attempts) == 1


def test_start_run_requires_login():
    request = RequestFactory().post("/runs/start/", {"operation": "scrape"})
    request.user = AnonymousUser()

    response = views.start_run(request)

    assert response.status_code == 302
    assert response.url.startswith("/admin/login/")


def test_start_run_queues_scrape_for_authenticated_user(monkeypatch):
    run = SimpleNamespace(pk=7, status="queued")
    request = RequestFactory().post("/runs/start/", {"operation": "scrape"})
    request.user = SimpleNamespace(is_authenticated=True)
    monkeypatch.setattr(views, "create_run", lambda operation, queued: run)

    response = views.start_run(request)

    assert response.status_code == 202
    payload = json.loads(response.content)
    assert payload["run_id"] == 7
    assert payload["status_url"] == "/runs/7/"


def test_start_run_rejects_unknown_operation():
    request = RequestFactory().post("/runs/start/", {"operation": "unknown"})
    request.user = SimpleNamespace(is_authenticated=True)

    response = views.start_run(request)

    assert response.status_code == 400
    assert json.loads(response.content) == {"error": "Choose a valid operation."}


def test_worker_retries_database_operational_errors(monkeypatch, caplog):
    attempts = []
    delays = []

    def check_stale_runs():
        attempts.append(None)
        if len(attempts) == 1:
            raise OperationalError("temporary DNS failure")

    monkeypatch.setattr(run_job_worker, "close_old_connections", lambda: None)
    monkeypatch.setattr(run_job_worker, "mark_stale_runs_failed", check_stale_runs)
    monkeypatch.setattr(run_job_worker, "claim_next_run", lambda: None)
    monkeypatch.setattr(run_job_worker.time, "sleep", delays.append)

    run_job_worker.Command().handle(once=True, poll_seconds=2)

    assert len(attempts) == 2
    assert delays == [1]
    assert "Database unavailable in run worker" in caplog.text


def test_worker_marks_run_failed_if_database_drops_during_execution(monkeypatch):
    delays = []
    run = SimpleNamespace(pk=42)
    claimed = [run, None]
    failed_run_ids = []

    monkeypatch.setattr(run_job_worker, "close_old_connections", lambda: None)
    monkeypatch.setattr(run_job_worker, "mark_stale_runs_failed", lambda: None)
    monkeypatch.setattr(run_job_worker, "claim_next_run", lambda: claimed.pop(0))

    def execute(_run):
        raise OperationalError("temporary connection loss")

    monkeypatch.setattr(run_job_worker, "execute_run", execute)
    monkeypatch.setattr(
        run_job_worker,
        "mark_worker_run_failed_after_database_error",
        failed_run_ids.append,
    )
    monkeypatch.setattr(run_job_worker.time, "sleep", delays.append)

    run_job_worker.Command().handle(once=True, poll_seconds=2)

    assert failed_run_ids == [42]
    assert delays == [1]


def test_worker_does_not_hide_schema_errors(monkeypatch):
    def raise_schema_error():
        raise ProgrammingError('relation "jobs_scraperun" does not exist')

    monkeypatch.setattr(run_job_worker, "close_old_connections", lambda: None)
    monkeypatch.setattr(run_job_worker, "mark_stale_runs_failed", raise_schema_error)

    with pytest.raises(ProgrammingError, match="jobs_scraperun"):
        run_job_worker.Command().handle(once=True, poll_seconds=2)
