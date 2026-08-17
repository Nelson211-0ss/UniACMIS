from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.curriculum.models import (
    Course,
    CurriculumCourse,
    CurriculumVersion,
    Department,
    Faculty,
    Prerequisite,
    Programme,
)
from apps.curriculum.services import curriculum_health


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0
    fields = ["code", "name", "head", "is_active"]
    autocomplete_fields = ["head"]
    show_change_link = True


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "dean", "department_count", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]
    autocomplete_fields = ["dean"]
    inlines = [DepartmentInline]

    @admin.display(description=_("departments"))
    def department_count(self, obj: Faculty) -> int:
        return obj.departments.count()


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "faculty", "head", "programme_count", "is_active"]
    list_filter = ["faculty", "is_active"]
    search_fields = ["code", "name"]
    autocomplete_fields = ["faculty", "head"]

    @admin.display(description=_("programmes"))
    def programme_count(self, obj: Department) -> int:
        return obj.programmes.count()


class CurriculumVersionInline(admin.TabularInline):
    model = CurriculumVersion
    extra = 0
    fields = ["version", "status", "effective_from", "effective_to"]
    show_change_link = True


@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "department",
        "award",
        "duration_years",
        "total_credits_required",
        "is_active",
    ]
    list_filter = ["award", "is_active", "department__faculty", "department"]
    search_fields = ["code", "name"]
    autocomplete_fields = ["department"]
    inlines = [CurriculumVersionInline]
    fieldsets = (
        (None, {"fields": ("department", "code", "name", "award", "description")}),
        (_("Duration and credits"), {"fields": ("duration_years", "total_credits_required")}),
        (
            _("Registration limits"),
            {
                "fields": ("min_credits_per_semester", "max_credits_per_semester"),
                "description": _("Enforced when students register for courses."),
            },
        ),
        (
            _("Admissions"),
            {
                "fields": ("entry_requirements", "is_active"),
                "description": _(
                    "Entry requirements are screened against applicants from Phase 2."
                ),
            },
        ),
    )


class CurriculumCourseInline(admin.TabularInline):
    model = CurriculumCourse
    extra = 0
    fields = [
        "course",
        "year_of_study",
        "semester_sequence",
        "is_core",
        "elective_group",
        "min_group_choices",
    ]
    autocomplete_fields = ["course"]


@admin.register(CurriculumVersion)
class CurriculumVersionAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "programme",
        "status",
        "effective_from",
        "effective_to",
        "core_credits",
        "health",
    ]
    list_filter = ["status", "programme__department__faculty"]
    search_fields = ["version", "programme__code", "programme__name"]
    autocomplete_fields = ["programme", "effective_from", "effective_to"]
    inlines = [CurriculumCourseInline]

    @admin.display(description=_("core credits"))
    def core_credits(self, obj: CurriculumVersion) -> str:
        return f"{obj.total_core_credits}/{obj.programme.total_credits_required}"

    @admin.display(description=_("configuration"))
    def health(self, obj: CurriculumVersion) -> str:
        report = curriculum_health(obj.pk)
        if report["healthy"]:
            return "✓ complete"
        problems = report["problems"]
        return f"⚠ {problems[0]}" if isinstance(problems, list) and problems else "⚠"


class PrerequisiteInline(admin.TabularInline):
    model = Prerequisite
    fk_name = "course"
    extra = 0
    fields = ["required_course", "minimum_grade_point", "is_concurrent_allowed"]
    autocomplete_fields = ["required_course"]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["code", "title", "department", "credit_hours", "level", "is_active"]
    list_filter = ["department__faculty", "department", "level", "is_active"]
    search_fields = ["code", "title"]
    autocomplete_fields = ["department"]
    inlines = [PrerequisiteInline]


@admin.register(Prerequisite)
class PrerequisiteAdmin(admin.ModelAdmin):
    list_display = ["course", "required_course", "minimum_grade_point", "is_concurrent_allowed"]
    search_fields = ["course__code", "required_course__code"]
    autocomplete_fields = ["course", "required_course"]
