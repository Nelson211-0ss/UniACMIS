"""Admissions admin — the committee's and registrar's working interface."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.admissions import services
from apps.admissions.eligibility import evaluate_entry_requirements
from apps.admissions.models import (
    Application,
    ApplicationDocument,
    ApplicationFeePayment,
    ApplicationReview,
)


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    fields = ["document_type", "title", "file", "verified_by", "verified_at"]
    readonly_fields = ["verified_by", "verified_at"]


class ApplicationReviewInline(admin.TabularInline):
    model = ApplicationReview
    extra = 0
    fields = ["reviewer", "score", "comments", "created_at"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["reviewer"]


class ApplicationFeePaymentInline(admin.TabularInline):
    model = ApplicationFeePayment
    extra = 0
    fields = ["provider", "reference", "amount", "currency", "status", "confirmed_at"]
    readonly_fields = ["confirmed_at"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = [
        "reference_number",
        "get_full_name",
        "programme",
        "status",
        "score",
        "fee_paid",
        "source",
        "created_at",
    ]
    list_filter = ["status", "source", "fee_paid", "programme__department__faculty", "programme"]
    search_fields = ["reference_number", "first_name", "last_name", "national_id_number", "email"]
    autocomplete_fields = [
        "programme",
        "intended_academic_year",
        "user",
        "entered_by",
        "reviewed_by",
    ]
    readonly_fields = [
        "reference_number",
        "score",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "student",
        "eligibility_check",
    ]
    inlines = [ApplicationDocumentInline, ApplicationReviewInline, ApplicationFeePaymentInline]
    actions = ["make_offer", "reject_application", "convert_accepted_to_student"]

    @admin.display(description=_("applicant"))
    def get_full_name(self, obj: Application) -> str:
        return obj.get_full_name()

    @admin.display(description=_("entry requirements"))
    def eligibility_check(self, obj: Application) -> str:
        warnings = evaluate_entry_requirements(obj.programme.entry_requirements, obj.previous_grade)
        return "; ".join(warnings) if warnings else "✓ meets stated minimum"

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = _("Edited in the admin")
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Make an offer (accepted applications only)"))
    def make_offer(self, request, queryset) -> None:
        self._decide(request, queryset, "offered")

    @admin.action(description=_("Reject selected applications"))
    def reject_application(self, request, queryset) -> None:
        self._decide(request, queryset, "rejected")

    def _decide(self, request, queryset, decision: str) -> None:
        count = 0
        for application in queryset:
            try:
                services.decide_application(
                    application,
                    decision,
                    decided_by=request.user,
                    reason=f"Decided from the admin bulk action ({decision}).",
                )
                count += 1
            except Exception as exc:
                messages.error(request, f"{application.reference_number}: {exc}")
        if count:
            messages.success(request, _("%(n)d application(s) updated.") % {"n": count})

    @admin.action(description=_("Convert accepted applications to student records"))
    def convert_accepted_to_student(self, request, queryset) -> None:
        count = 0
        for application in queryset:
            try:
                services.convert_to_student(application, actor=request.user)
                count += 1
            except Exception as exc:
                messages.error(request, f"{application.reference_number}: {exc}")
        if count:
            messages.success(request, _("%(n)d application(s) converted.") % {"n": count})


@admin.register(ApplicationReview)
class ApplicationReviewAdmin(admin.ModelAdmin):
    list_display = ["application", "reviewer", "score", "created_at"]
    search_fields = ["application__reference_number", "reviewer__email"]
    autocomplete_fields = ["application", "reviewer"]


@admin.register(ApplicationFeePayment)
class ApplicationFeePaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "application", "amount", "currency", "status", "confirmed_at"]
    list_filter = ["status", "currency"]
    search_fields = ["reference", "application__reference_number"]
    autocomplete_fields = ["application"]
    readonly_fields = ["confirmed_at"]
