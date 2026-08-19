"""Attendance admin — mostly for support/inspection; a lecturer takes the
register through the app, not here."""

from __future__ import annotations

from django.contrib import admin

from apps.attendance.models import AttendanceWaiver, SessionRecord


@admin.register(SessionRecord)
class SessionRecordAdmin(admin.ModelAdmin):
    list_display = ["registration", "timetable_entry", "session_date", "status", "recorded_by"]
    list_filter = ["status", "session_date"]
    search_fields = ["registration__student__student_id", "registration__student__last_name"]
    autocomplete_fields = ["timetable_entry", "registration", "recorded_by"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(AttendanceWaiver)
class AttendanceWaiverAdmin(admin.ModelAdmin):
    list_display = ["registration", "granted_by", "created_at"]
    search_fields = ["registration__student__student_id"]
    autocomplete_fields = ["registration", "granted_by"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = obj.reason
        super().save_model(request, obj, form, change)
