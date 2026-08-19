"""Enrollment admin — class lists and registration overrides for the registrar."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.enrollment import services
from apps.enrollment.models import CourseRegistration


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "course",
        "semester",
        "status",
        "is_repeat",
        "hold_override_by",
        "created_at",
    ]
    list_filter = ["status", "is_repeat", "semester", "course__department__faculty"]
    search_fields = ["student__student_id", "student__last_name", "course__code"]
    autocomplete_fields = ["student", "course", "semester", "registered_by"]
    readonly_fields = [
        "is_repeat",
        "registered_by",
        "dropped_at",
        "hold_override_by",
        "completed_by",
        "completed_at",
    ]
    actions = ["record_completion"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = _("Edited in the admin")
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Record as completed (transfer credit / legacy record)"))
    def record_completion(self, request, queryset) -> None:
        count = 0
        for registration in queryset:
            try:
                services.record_prior_completion(
                    registration,
                    actor=request.user,
                    reason="Recorded from the admin bulk action.",
                )
                count += 1
            except Exception as exc:
                messages.error(request, f"{registration}: {exc}")
        if count:
            messages.success(request, _("%(n)d registration(s) marked completed.") % {"n": count})
