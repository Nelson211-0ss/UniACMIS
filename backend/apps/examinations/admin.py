"""Examinations admin — for support/inspection and Senate's paper trail; day
to day mark entry happens through the app."""

from __future__ import annotations

from django.contrib import admin

from apps.examinations.models import Assessment, GradeAppeal, Mark, ResultApproval


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = [
        "course",
        "name",
        "weight_percent",
        "max_score",
        "sequence",
        "grade_entry_deadline",
    ]
    list_filter = ["course__department__faculty"]
    search_fields = ["course__code", "name"]
    autocomplete_fields = ["course"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = [
        "registration",
        "assessment",
        "score",
        "moderated_score",
        "is_late",
        "is_irregular",
    ]
    list_filter = ["is_late", "is_irregular", "assessment__course"]
    search_fields = ["registration__student__student_id", "registration__student__last_name"]
    autocomplete_fields = ["registration", "assessment", "moderated_by", "entered_by"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(GradeAppeal)
class GradeAppealAdmin(admin.ModelAdmin):
    list_display = [
        "registration",
        "assessment",
        "status",
        "submitted_by",
        "decided_by",
        "created_at",
    ]
    list_filter = ["status"]
    autocomplete_fields = ["registration", "assessment", "submitted_by", "decided_by"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(ResultApproval)
class ResultApprovalAdmin(admin.ModelAdmin):
    list_display = ["semester", "programme", "status", "approved_by", "published_by"]
    list_filter = ["status", "semester"]
    autocomplete_fields = ["semester", "programme", "approved_by", "published_by"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)
