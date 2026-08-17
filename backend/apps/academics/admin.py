"""Admin for institutional configuration — the registrar's setup screens."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.academics.models import (
    AcademicYear,
    GradeBand,
    GradingScale,
    Institution,
    Semester,
)


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ["name", "mohest_code", "default_currency", "attendance_threshold_percent"]
    fieldsets = (
        (None, {"fields": ("name", "short_name", "mohest_code")}),
        (_("Contact"), {"fields": ("address", "phone", "email", "website")}),
        (_("Branding"), {"fields": ("logo", "letterhead")}),
        (
            _("Currency"),
            {
                "fields": ("default_currency", "secondary_currency"),
                "description": _(
                    "The base currency is what balances are reported in. Amounts in "
                    "another currency always store the exchange rate used."
                ),
            },
        ),
        (
            _("Identifiers and thresholds"),
            {
                "fields": (
                    "student_id_template",
                    "staff_id_template",
                    "attendance_threshold_percent",
                    "timezone",
                )
            },
        ),
    )

    def has_add_permission(self, request) -> bool:
        # Single institution per instance (multi-campus is deferred, D-1).
        return not Institution.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class SemesterInline(admin.TabularInline):
    model = Semester
    extra = 0
    fields = [
        "sequence",
        "name",
        "teaching_start",
        "teaching_end",
        "registration_opens",
        "registration_closes",
        "add_drop_closes",
        "exam_start",
        "exam_end",
        "is_current",
    ]


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_current", "semester_count"]
    list_filter = ["is_current"]
    search_fields = ["name"]
    inlines = [SemesterInline]

    @admin.display(description=_("semesters"))
    def semester_count(self, obj: AcademicYear) -> int:
        return obj.semesters.count()


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "teaching_start",
        "teaching_end",
        "registration_window",
        "is_current",
    ]
    list_filter = ["is_current", "academic_year"]
    search_fields = ["name", "academic_year__name"]
    autocomplete_fields = ["academic_year"]

    @admin.display(description=_("registration window"))
    def registration_window(self, obj: Semester) -> str:
        if not obj.registration_opens or not obj.registration_closes:
            return _("not set — registration closed")
        return f"{obj.registration_opens:%d %b} → {obj.registration_closes:%d %b %Y}"


class GradeBandInlineFormSet(forms.BaseInlineFormSet):
    """Validates the bands together, not one at a time.

    Completeness and non-overlap are properties of the whole set, so they can only
    be checked here. Letting a scale save with a gap is how a mark ends up with no
    grade at all.
    """

    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return

        bands = [
            form.instance
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
        ]
        if not bands:
            return

        scale = self.instance
        try:
            scale.validate_bands(bands)
        except ValidationError as exc:
            raise ValidationError(exc.messages) from exc


class GradeBandInline(admin.TabularInline):
    model = GradeBand
    formset = GradeBandInlineFormSet
    extra = 0
    fields = ["letter", "min_percent", "max_percent", "grade_point", "is_pass", "description"]
    ordering = ["-min_percent"]


@admin.register(GradingScale)
class GradingScaleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "max_grade_point",
        "pass_grade_point",
        "band_count",
        "is_default",
        "is_locked",
        "coverage",
    ]
    list_filter = ["is_default", "is_locked"]
    search_fields = ["name"]
    inlines = [GradeBandInline]

    @admin.display(description=_("bands"))
    def band_count(self, obj: GradingScale) -> int:
        return obj.bands.count()

    @admin.display(description=_("validity"))
    def coverage(self, obj: GradingScale) -> str:
        try:
            obj.validate_bands()
        except ValidationError as exc:
            return f"⚠ {exc.messages[0]}"
        return "✓ covers 0–100"

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.is_locked:
            return [f.name for f in obj._meta.fields if f.name != "id"]
        return super().get_readonly_fields(request, obj)


@admin.register(GradeBand)
class GradeBandAdmin(admin.ModelAdmin):
    list_display = ["scale", "letter", "min_percent", "max_percent", "grade_point", "is_pass"]
    list_filter = ["scale", "is_pass"]
    search_fields = ["letter", "scale__name"]
    autocomplete_fields = ["scale"]
