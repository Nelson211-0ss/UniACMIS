from __future__ import annotations

from django.contrib import admin

from apps.alumni.models import AlumniEvent, AlumniProfile


@admin.register(AlumniProfile)
class AlumniProfileAdmin(admin.ModelAdmin):
    list_display = ["student", "employment_status", "current_employer", "is_contactable"]
    list_filter = ["employment_status", "is_contactable"]
    search_fields = ["student__student_id", "student__last_name", "current_employer"]
    autocomplete_fields = ["student"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(AlumniEvent)
class AlumniEventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_date", "location"]
    list_filter = ["event_date"]
    search_fields = ["title", "location"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)
