from django.contrib import admin

from .models import Employer, Job


@admin.register(Employer)
class EmployerAdmin(admin.ModelAdmin):
    list_display = ("name", "adapter", "active", "board_url")
    list_filter = ("adapter", "active")
    search_fields = ("name",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "employer", "location", "status", "score", "filter_reason", "first_seen")
    list_filter = ("status", "employer")
    search_fields = ("title", "description", "location")
    ordering = ("-score", "-first_seen")
    actions = ["mark_saved", "mark_ignored", "mark_new"]

    @admin.action(description="User selected jobs as Saved")
    def mark_saved(self, request, queryset):
        queryset.update(status=Job.Status.SAVED)

    @admin.action(description="User selected jobs as Ignored")
    def mark_ignored(self, request, queryset):
        queryset.update(status=Job.Status.IGNORED)

    @admin.action(description="User selected jobs as New")
    def mark_new(self, request, queryset):
        queryset.update(status=Job.Status.NEW)
