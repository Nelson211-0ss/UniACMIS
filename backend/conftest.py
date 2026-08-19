"""Shared fixtures.

Deliberately builds a *real* institution — calendar, grading scale, faculty
hierarchy and a curriculum — rather than mocking configuration. Most of the bugs
worth catching here come from configuration being absent or inconsistent, and a
mock would hide exactly those.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicYear,
    GradeBand,
    GradingScale,
    Institution,
    Semester,
)
from apps.accounts.models import User
from apps.accounts.services import grant_role
from apps.core.providers import holds as hold_providers
from apps.curriculum.models import (
    Award,
    Course,
    CurriculumCourse,
    CurriculumStatus,
    CurriculumVersion,
    Department,
    Faculty,
    Programme,
)
from apps.registry.models import Gender, StaffCategory, StaffProfile
from apps.registry.services import create_student
from tests.constants import PASSWORD


def _aware(day: date, hour: int = 12) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


# --------------------------------------------------------------------- policy


@pytest.fixture
def roles(db):
    """Apply the RBAC policy. Almost every test needs it."""
    call_command("seed_roles", verbosity=0)


# -------------------------------------------------------------- configuration


@pytest.fixture
def institution(db) -> Institution:
    return Institution.objects.create(
        name="Test University",
        short_name="TU",
        mohest_code="SSD-TU-001",
        student_id_template="{faculty}/{programme}/{year}/{seq:04d}",
    )


@pytest.fixture
def academic_year(db) -> AcademicYear:
    return AcademicYear.objects.create(
        name="2026/2027",
        start_date=date(2026, 9, 1),
        end_date=date(2027, 7, 31),
        is_current=True,
    )


@pytest.fixture
def semester(academic_year) -> Semester:
    """A semester with registration currently open."""
    today = timezone.localdate()
    return Semester.objects.create(
        academic_year=academic_year,
        sequence=1,
        name="Semester 1",
        teaching_start=today,
        teaching_end=today + timedelta(days=100),
        exam_start=today + timedelta(days=110),
        exam_end=today + timedelta(days=124),
        registration_opens=_aware(today - timedelta(days=7)),
        registration_closes=_aware(today + timedelta(days=7)),
        add_drop_closes=_aware(today + timedelta(days=21)),
        is_current=True,
    )


@pytest.fixture
def grading_scale(db) -> GradingScale:
    """A valid 4.00 scale covering 0–100 with no gaps."""
    scale = GradingScale.objects.create(
        name="Test 4.00 scale",
        max_grade_point=Decimal("4.00"),
        pass_grade_point=Decimal("2.00"),
        is_default=True,
    )
    bands = [
        ("A", "70.00", "100.00", "4.00", True),
        ("B+", "65.00", "69.99", "3.50", True),
        ("B", "60.00", "64.99", "3.00", True),
        ("C+", "55.00", "59.99", "2.50", True),
        ("C", "50.00", "54.99", "2.00", True),
        ("D+", "45.00", "49.99", "1.50", False),
        ("D", "40.00", "44.99", "1.00", False),
        ("F", "0.00", "39.99", "0.00", False),
    ]
    for letter, low, high, points, is_pass in bands:
        GradeBand.objects.create(
            scale=scale,
            letter=letter,
            min_percent=Decimal(low),
            max_percent=Decimal(high),
            grade_point=Decimal(points),
            is_pass=is_pass,
        )
    return scale


# ------------------------------------------------------------------ structure


@pytest.fixture
def faculty(institution) -> Faculty:
    return Faculty.objects.create(institution=institution, code="ENG", name="Engineering")


@pytest.fixture
def department(faculty) -> Department:
    return Department.objects.create(faculty=faculty, code="CVE", name="Civil Engineering")


@pytest.fixture
def programme(department) -> Programme:
    return Programme.objects.create(
        department=department,
        code="CIV",
        name="BSc Civil Engineering",
        award=Award.BACHELOR,
        duration_years=5,
        total_credits_required=180,
        min_credits_per_semester=12,
        max_credits_per_semester=24,
    )


@pytest.fixture
def curriculum_version(programme, academic_year) -> CurriculumVersion:
    return CurriculumVersion.objects.create(
        programme=programme,
        version="2026-v1",
        status=CurriculumStatus.ACTIVE,
        effective_from=academic_year,
    )


@pytest.fixture
def course(department) -> Course:
    return Course.objects.create(
        department=department, code="CVE101", title="Engineering Drawing", credit_hours=3, level=1
    )


@pytest.fixture
def curriculum_course(curriculum_version, course) -> CurriculumCourse:
    return CurriculumCourse.objects.create(
        curriculum_version=curriculum_version, course=course, year_of_study=1, semester_sequence=1
    )


# ---------------------------------------------------------------------- users


@pytest.fixture
def user_factory(db):
    counter = {"n": 0}

    def _make(role: str | None = None, **kwargs) -> User:
        counter["n"] += 1
        n = counter["n"]
        defaults = {
            "email": kwargs.pop("email", f"user{n}@test.ss"),
            "first_name": kwargs.pop("first_name", "Test"),
            "last_name": kwargs.pop("last_name", f"User{n}"),
        }
        user = User.objects.create_user(password=PASSWORD, **defaults, **kwargs)
        if role:
            grant_role(user, role, reason="test fixture")
        return user

    return _make


@pytest.fixture
def staff_factory(user_factory, department):
    counter = {"n": 0}

    def _make(role: str, *, dept: Department | None = None, **kwargs) -> User:
        counter["n"] += 1
        user = user_factory(role=role, **kwargs)
        StaffProfile.objects.create(
            user=user,
            staff_number=f"STF/2026/{counter['n']:04d}",
            department=dept if dept is not None else department,
            staff_category=StaffCategory.ACADEMIC,
        )
        return user

    return _make


@pytest.fixture
def registrar(roles, user_factory) -> User:
    return user_factory(role="registrar", email="registrar@test.ss")


@pytest.fixture
def lecturer(roles, staff_factory) -> User:
    return staff_factory("lecturer", email="lecturer@test.ss")


@pytest.fixture
def hod(roles, staff_factory) -> User:
    return staff_factory("hod", email="hod@test.ss")


@pytest.fixture
def finance_officer(roles, user_factory) -> User:
    return user_factory(role="finance", email="finance@test.ss")


@pytest.fixture
def examinations_officer(roles, user_factory) -> User:
    return user_factory(role="examinations", email="examinations@test.ss")


@pytest.fixture
def senate_member(roles, user_factory) -> User:
    return user_factory(role="senate", email="senate@test.ss")


@pytest.fixture
def hr_officer(roles, user_factory) -> User:
    return user_factory(role="hr", email="hr@test.ss")


@pytest.fixture
def librarian(roles, user_factory) -> User:
    return user_factory(role="library", email="librarian@test.ss")


@pytest.fixture
def hostel_officer(roles, user_factory) -> User:
    return user_factory(role="hostel", email="hostel@test.ss")


@pytest.fixture
def management_officer(roles, user_factory) -> User:
    return user_factory(role="management", email="management@test.ss")


@pytest.fixture
def ict_admin(roles, user_factory) -> User:
    return user_factory(role="ict_admin", email="ict@test.ss")


# -------------------------------------------------------------------- clients


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def as_user(api):
    def _login(user: User) -> APIClient:
        api.force_authenticate(user=user)
        return api

    return _login


# ------------------------------------------------------------------- students


@pytest.fixture
def student(programme, curriculum_version, academic_year, institution):
    return create_student(
        programme_id=programme.pk,
        entry_academic_year_id=academic_year.pk,
        first_name="Aluel",
        last_name="Deng",
        gender=Gender.FEMALE,
        curriculum_version_id=curriculum_version.pk,
        national_id_number="SSD00000001",
        reason="test fixture",
    )


@pytest.fixture
def student_portal_user(roles, user_factory, student) -> User:
    """Links the registry `student` fixture to a portal account holding the
    `student` role, so `ScopedQuerysetMixin`'s self-scoping filters match."""
    user = user_factory(role="student", email="student-portal@test.ss")
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture(autouse=True)
def _clean_demo_holds():
    """Stop a fee hold set by one test leaking into the next."""
    hold_providers.clear_demo_balances()
    yield
    hold_providers.clear_demo_balances()
