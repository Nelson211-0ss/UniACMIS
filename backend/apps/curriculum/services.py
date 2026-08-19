"""
Public service API for the curriculum module.

Other modules call these functions; they do not import curriculum models. That is
what lets enrollment, examinations and reporting be written against a stable
surface (ARCHITECTURE §4, rule 2).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from apps.curriculum.models import (
    Course,
    CurriculumCourse,
    CurriculumStatus,
    CurriculumVersion,
    Prerequisite,
    Programme,
)


@dataclass(frozen=True)
class UnmetPrerequisite:
    course_code: str
    required_course_code: str
    reason: str


def active_curriculum_for(programme_id: int) -> CurriculumVersion | None:
    return CurriculumVersion.objects.filter(
        programme_id=programme_id, status=CurriculumStatus.ACTIVE
    ).first()


def courses_for(
    curriculum_version_id: int,
    *,
    year_of_study: int | None = None,
    semester_sequence: int | None = None,
    core_only: bool = False,
) -> list[CurriculumCourse]:
    """The courses prescribed by a curriculum, optionally for one period."""
    queryset = CurriculumCourse.objects.filter(
        curriculum_version_id=curriculum_version_id
    ).select_related("course")

    if year_of_study is not None:
        queryset = queryset.filter(year_of_study=year_of_study)
    if semester_sequence is not None:
        queryset = queryset.filter(semester_sequence=semester_sequence)
    if core_only:
        queryset = queryset.filter(is_core=True)

    return list(queryset)


def unmet_prerequisites(
    course_ids: Iterable[int],
    passed: dict[int, Decimal | None],
    *,
    concurrent_ids: Iterable[int] = (),
) -> list[UnmetPrerequisite]:
    """Which prerequisites are not satisfied.

    `passed` maps course id → grade point achieved (None when the grade point is
    unknown but the course was passed). `concurrent_ids` are courses being
    registered in the same semester, which satisfy a prerequisite only where it is
    explicitly marked concurrent-friendly.

    Pure with respect to the student: it takes their history as data, so Phase 2
    can call it without this module knowing what a student is.
    """
    course_ids = list(course_ids)
    if not course_ids:
        return []

    concurrent = set(concurrent_ids)
    failures: list[UnmetPrerequisite] = []

    links = Prerequisite.objects.filter(course_id__in=course_ids).select_related(
        "course", "required_course"
    )

    for link in links:
        required_id = link.required_course_id

        if required_id in passed:
            achieved = passed[required_id]
            if (
                link.minimum_grade_point is not None
                and achieved is not None
                and achieved < link.minimum_grade_point
            ):
                failures.append(
                    UnmetPrerequisite(
                        course_code=link.course.code,
                        required_course_code=link.required_course.code,
                        reason=(
                            f"needs at least {link.minimum_grade_point} grade point in "
                            f"{link.required_course.code}, achieved {achieved}"
                        ),
                    )
                )
            continue

        if link.is_concurrent_allowed and required_id in concurrent:
            continue

        failures.append(
            UnmetPrerequisite(
                course_code=link.course.code,
                required_course_code=link.required_course.code,
                reason=f"{link.required_course.code} has not been passed",
            )
        )

    return failures


def total_credits(course_ids: Iterable[int]) -> int:
    return sum(
        Course.objects.filter(id__in=list(course_ids)).values_list("credit_hours", flat=True)
    )


def admission_quota_rules(programme_id: int) -> dict[str, object]:
    """A programme's merit-list seat configuration (FR-ADM-06), read without
    the caller importing the `Programme` model directly."""
    return (
        Programme.objects.values_list("admission_quota_rules", flat=True).get(pk=programme_id) or {}
    )


def id_tokens_for_programme(programme_id: int) -> dict[str, str]:
    """Faculty and programme codes used to build a student ID (FR-REG-01).

    Exposed as a service so `registry` can generate IDs without importing
    curriculum models.
    """
    programme = Programme.objects.select_related("department__faculty").get(pk=programme_id)
    return {
        "faculty": programme.department.faculty.code,
        "programme": programme.code,
        "department": programme.department.code,
    }


def credit_limits(programme_id: int) -> tuple[int, int]:
    """(minimum, maximum) credits per semester for a programme (FR-ENR-02)."""
    programme = Programme.objects.get(pk=programme_id)
    return programme.min_credits_per_semester, programme.max_credits_per_semester


def curriculum_health(curriculum_version_id: int) -> dict[str, object]:
    """Report configuration problems that would otherwise surface years later."""
    version = CurriculumVersion.objects.select_related("programme").get(pk=curriculum_version_id)
    entries = courses_for(curriculum_version_id)

    problems: list[str] = []

    shortfall = version.credit_shortfall()
    if shortfall > 0:
        problems.append(
            f"Core courses total {version.total_core_credits} credits but the programme "
            f"requires {version.programme.total_credits_required} — short by {shortfall}. "
            "Students could not graduate on core courses alone."
        )

    if not entries:
        problems.append("No courses are attached to this curriculum version.")

    duration = version.programme.duration_years
    covered_years = {entry.year_of_study for entry in entries}
    missing_years = sorted(set(range(1, duration + 1)) - covered_years)
    if missing_years:
        problems.append(f"No courses defined for year(s) {missing_years}.")

    return {
        "curriculum_version": str(version),
        "course_count": len(entries),
        "core_credits": version.total_core_credits,
        "required_credits": version.programme.total_credits_required,
        "problems": problems,
        "healthy": not problems,
    }
