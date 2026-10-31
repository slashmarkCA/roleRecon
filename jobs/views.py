from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET

from .models import Employer, EmployerRunResult, Job, ScrapeRun
from .run_service import create_run

LIST_LIMIT = 200


@login_required(login_url="/admin/login/")
def job_list(request):
    """Two-pane page: filtered job list on the left, selected job on the right."""
    status = request.GET.get("status", Job.Status.NEW.value)
    employer_id = request.GET.get("employer", "")
    q = request.GET.get("q", "").strip()

    jobs = Job.objects.select_related("employer")
    if status != "all":
        jobs = jobs.filter(status=status)
    if employer_id.isdigit():
        jobs = jobs.filter(employer_id=int(employer_id))
    if q:
        jobs = jobs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    jobs = jobs.order_by("-score", "-first_seen")[:LIST_LIMIT]

    selected = None
    job_id = request.GET.get("job", "")
    if job_id.isdigit():
        selected = Job.objects.select_related("employer").filter(pk=int(job_id)).first()

    counts = dict(Job.objects.values_list("status").annotate(n=Count("id")))
    statuses = [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in Job.Status.choices
    ]

    context = {
        "jobs": jobs,
        "selected": selected,
        "status": status,
        "employer_id": employer_id,
        "q": q,
        "statuses": statuses,
        "total": sum(counts.values()),
        "employers": Employer.objects.all(),
        "base_qs": urlencode({"status": status, "employer": employer_id, "q": q}),
        "full_qs": request.GET.urlencode(),
        "latest_run": ScrapeRun.objects.first(),
    }
    return render(request, "jobs/job_list.html", context)


@require_POST
@login_required(login_url="/admin/login/")
def set_status(request, pk):
    job = get_object_or_404(Job, pk=pk)
    new_status = request.POST.get("status", "")
    if new_status in Job.Status.values:
        job.status = new_status
        job.save(update_fields=["status"])
    return redirect(f"{reverse('job_list')}?{request.POST.get('qs', '')}")


@require_POST
@login_required(login_url="/admin/login/")
def bulk_set_status(request):
    new_status = request.POST.get("status", "")
    if new_status not in {
        Job.Status.NEW,
        Job.Status.SAVED,
        Job.Status.APPLIED,
        Job.Status.IGNORED,
    }:
        return HttpResponseBadRequest("Choose a valid job status.")

    raw_ids = request.POST.getlist("job_ids")
    if not raw_ids or len(raw_ids) > LIST_LIMIT:
        return HttpResponseBadRequest(f"Select between 1 and {LIST_LIMIT} jobs.")
    if any(not value.isdigit() or int(value) < 1 for value in raw_ids):
        return HttpResponseBadRequest("Selected job IDs must be positive integers.")

    job_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    jobs = Job.objects.filter(pk__in=job_ids)
    if jobs.count() != len(job_ids):
        return HttpResponseBadRequest("One or more selected jobs could not be found.")
    jobs.update(status=new_status)
    return redirect(f"{reverse('job_list')}?{request.POST.get('qs', '')}")


@require_POST
@login_required(login_url="/admin/login/")
def start_run(request):
    operation = request.POST.get("operation", "")
    if operation not in ScrapeRun.Operation.values:
        return JsonResponse({"error": "Choose a valid operation."}, status=400)
    try:
        run = create_run(operation, queued=True)
    except IntegrityError:
        active_run = ScrapeRun.objects.filter(
            status__in=[ScrapeRun.Status.QUEUED, ScrapeRun.Status.RUNNING]
        ).first()
        if active_run is None:
            raise
        return JsonResponse(
            {
                "error": "A run is already queued or running.",
                "run_id": active_run.pk,
                "status_url": reverse("run_status", args=[active_run.pk]),
            },
            status=409,
        )
    return JsonResponse({
        "run_id": run.pk,
        "status": run.status,
        "status_url": reverse("run_status", args=[run.pk]),
    }, status=202)


@require_GET
@login_required(login_url="/admin/login/")
def run_status(request, run_id):
    run = get_object_or_404(ScrapeRun, pk=run_id)
    results = [
        {
            "employer": result.employer_name,
            "status": result.status,
            "summary": result.summary,
            "error": result.error_summary,
        }
        for result in run.employer_results.all()
    ]
    return JsonResponse({
        "id": run.pk,
        "operation": run.operation,
        "status": run.status,
        "summary": run.summary,
        "error": run.error_summary,
        "progress_current": run.progress_current,
        "progress_total": run.progress_total,
        "progress_message": run.progress_message,
        "results": results,
    })
