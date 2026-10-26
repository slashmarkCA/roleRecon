from django.urls import path

from . import views

urlpatterns = [
    path("", views.job_list, name="job_list"),
    path("job/<int:pk>/status/", views.set_status, name="set_status"),
    path("runs/start/", views.start_run, name="start_run"),
    path("runs/<int:run_id>/", views.run_status, name="run_status"),
]
