from urllib.parse import urlencode

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Employer, Job

LIST_LIMIT = 200


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
    }
    return render(request, "jobs/job_list.html", context)


@require_POST
def set_status(request, pk):
    job = get_object_or_404(Job, pk=pk)
    new_status = request.POST.get("status", "")
    if new_status in Job.Status.values:
        job.status = new_status
        job.save(update_fields=["status"])
    return redirect(f"{reverse('job_list')}?{request.POST.get('qs', '')}")
