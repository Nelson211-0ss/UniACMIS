"""
Seed a working demo institution.

    python manage.py seed_demo

**Development only** — refuses to run with DEBUG=False. It creates named accounts
with known passwords, which is exactly what must never exist in production.

What it produces is a system a registrar can actually click around: two faculties,
four programmes with versioned curricula and prerequisites, a configured calendar
and grading scale, one account per role, and a cohort of students — including some
who will show a fee hold, so the blocked-registration path is visible without any
extra setup.
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import (
    AcademicYear,
    GradeBand,
    GradingScale,
    Institution,
    Semester,
)
from apps.accounts.models import User
from apps.accounts.roles import ROLES
from apps.accounts.services import grant_role
from apps.core import context
from apps.core.choices import SouthSudanState
from apps.curriculum.models import (
    Award,
    Course,
    CurriculumCourse,
    CurriculumStatus,
    CurriculumVersion,
    Department,
    Faculty,
    Prerequisite,
    Programme,
)
from apps.registry.models import (
    AcademicRank,
    Gender,
    NextOfKin,
    Sponsor,
    SponsorshipType,
    SponsorType,
    StaffCategory,
    StaffProfile,
)
from apps.registry.services import create_student

DEMO_PASSWORD = "UniACMIS#Demo2026"

# 4.00-point scale. The exact boundaries are an institutional policy decision
# (SRS §8 open item 4) — this is a documented default, not a claim about any
# particular university's regulations.
GRADE_BANDS = [
    ("A", "70.00", "100.00", "4.00", True, "Excellent"),
    ("B+", "65.00", "69.99", "3.50", True, "Very good"),
    ("B", "60.00", "64.99", "3.00", True, "Good"),
    ("C+", "55.00", "59.99", "2.50", True, "Satisfactory"),
    ("C", "50.00", "54.99", "2.00", True, "Pass"),
    ("D+", "45.00", "49.99", "1.50", False, "Marginal fail"),
    ("D", "40.00", "44.99", "1.00", False, "Fail"),
    ("F", "0.00", "39.99", "0.00", False, "Fail"),
]

FIRST_NAMES_F = [
    "Aluel",
    "Nyandeng",
    "Achol",
    "Rebecca",
    "Awut",
    "Poni",
    "Aciek",
    "Nyibol",
    "Adau",
    "Suzan",
    "Ayen",
    "Josephine",
    "Akuol",
    "Mary",
    "Nyakuoth",
]
FIRST_NAMES_M = [
    "Deng",
    "Mabior",
    "Wani",
    "Lado",
    "Chol",
    "Gatluak",
    "Okello",
    "Majok",
    "Santino",
    "Peter",
    "Jok",
    "Emmanuel",
    "Riek",
    "Taban",
    "Lual",
]
MIDDLE_NAMES = ["Deng", "Wani", "Chol", "Lado", "Majok", "Okot", "Bol", "Kuol", "", ""]
LAST_NAMES = [
    "Deng",
    "Malual",
    "Juuk",
    "Lomoro",
    "Ayuel",
    "Gatkuoth",
    "Ochan",
    "Kiir",
    "Aleu",
    "Modi",
    "Nyuon",
    "Bashir",
    "Tombe",
    "Marial",
    "Odongo",
]

FACULTIES = [
    ("ENG", "Faculty of Engineering and Architecture"),
    ("SCI", "Faculty of Science and Technology"),
]

DEPARTMENTS = [
    ("CVE", "Department of Civil Engineering", "ENG"),
    ("EEE", "Department of Electrical Engineering", "ENG"),
    ("CSC", "Department of Computer Science", "SCI"),
    ("MTH", "Department of Mathematics and Statistics", "SCI"),
]

PROGRAMMES = [
    ("CIV", "Bachelor of Science in Civil Engineering", "CVE", Award.BACHELOR, 5, 180),
    ("ELE", "Bachelor of Science in Electrical Engineering", "EEE", Award.BACHELOR, 5, 180),
    ("BCS", "Bachelor of Science in Computer Science", "CSC", Award.BACHELOR, 4, 144),
    ("STA", "Bachelor of Science in Statistics", "MTH", Award.BACHELOR, 4, 144),
]

# code, title, dept, credits, level, (year, semester)
COURSES = [
    ("MTH101", "Calculus I", "MTH", 4, 1, 1, 1),
    ("MTH102", "Calculus II", "MTH", 4, 1, 1, 2),
    ("MTH201", "Linear Algebra", "MTH", 3, 2, 2, 1),
    ("STA101", "Introduction to Statistics", "MTH", 3, 1, 1, 2),
    ("STA201", "Probability Theory", "MTH", 4, 2, 2, 1),
    ("CSC101", "Introduction to Programming", "CSC", 4, 1, 1, 1),
    ("CSC102", "Data Structures", "CSC", 4, 1, 1, 2),
    ("CSC201", "Algorithms", "CSC", 4, 2, 2, 1),
    ("CSC202", "Database Systems", "CSC", 3, 2, 2, 2),
    ("CSC301", "Operating Systems", "CSC", 4, 3, 3, 1),
    ("CSC302", "Software Engineering", "CSC", 3, 3, 3, 2),
    ("CVE101", "Engineering Drawing", "CVE", 3, 1, 1, 1),
    ("CVE201", "Strength of Materials", "CVE", 4, 2, 2, 1),
    ("CVE202", "Fluid Mechanics", "CVE", 4, 2, 2, 2),
    ("CVE301", "Structural Analysis", "CVE", 4, 3, 3, 1),
    ("EEE101", "Basic Electrical Circuits", "EEE", 4, 1, 1, 1),
    ("EEE201", "Electronics I", "EEE", 4, 2, 2, 1),
    ("EEE202", "Electromagnetic Fields", "EEE", 3, 2, 2, 2),
    ("EEE301", "Power Systems", "EEE", 4, 3, 3, 1),
    ("GST101", "Communication Skills", "CSC", 2, 1, 1, 1),
    ("GST102", "Development Studies", "MTH", 2, 1, 1, 2),
]

PREREQUISITES = [
    ("MTH102", "MTH101", None),
    ("MTH201", "MTH102", None),
    ("STA201", "STA101", None),
    ("CSC102", "CSC101", None),
    ("CSC201", "CSC102", "2.00"),
    ("CSC301", "CSC201", None),
    ("CVE201", "MTH101", None),
    ("CVE301", "CVE201", "2.00"),
    ("EEE201", "EEE101", None),
    ("EEE301", "EEE201", None),
]

STAFF_ROLES = {
    "registrar": ("Grace", "Ayen", StaffCategory.ADMINISTRATIVE, AcademicRank.NOT_APPLICABLE, None),
    "finance": ("Samuel", "Lado", StaffCategory.ADMINISTRATIVE, AcademicRank.NOT_APPLICABLE, None),
    "examinations": (
        "Martha",
        "Nyibol",
        StaffCategory.ADMINISTRATIVE,
        AcademicRank.NOT_APPLICABLE,
        None,
    ),
    "senate": ("Prof. John", "Kiir", StaffCategory.ACADEMIC, AcademicRank.PROFESSOR, "CSC"),
    "hr": ("Betty", "Modi", StaffCategory.ADMINISTRATIVE, AcademicRank.NOT_APPLICABLE, None),
    "library": ("Paul", "Tombe", StaffCategory.SUPPORT, AcademicRank.NOT_APPLICABLE, None),
    "hostel": ("Rose", "Aleu", StaffCategory.SUPPORT, AcademicRank.NOT_APPLICABLE, None),
    "ict_admin": (
        "Daniel",
        "Ochan",
        StaffCategory.ADMINISTRATIVE,
        AcademicRank.NOT_APPLICABLE,
        None,
    ),
    "management": ("Prof. Anne", "Marial", StaffCategory.ACADEMIC, AcademicRank.PROFESSOR, None),
    "lecturer": ("James", "Malual", StaffCategory.ACADEMIC, AcademicRank.LECTURER, "CSC"),
    "hod": ("Dr. Michael", "Juuk", StaffCategory.ACADEMIC, AcademicRank.SENIOR_LECTURER, "CSC"),
}


class Command(BaseCommand):
    help = "Seed a demo institution, curriculum, staff and students (development only)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--students", type=int, default=30, help="How many students to create.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if data already exists (adds to it rather than resetting).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo creates accounts with published passwords and must never run "
                "in production. Use `seed_roles` there instead."
            )

        if Institution.objects.exists() and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    "An institution already exists. Re-run with --force to add demo data to it."
                )
            )
            return

        random.seed(20260817)  # reproducible demo data

        # Attribute every seeded change to `system` rather than to nobody.
        with context.acting_as(None):
            self._seed(options["students"])

    @transaction.atomic
    def _seed(self, student_count: int) -> None:
        institution = self._institution()
        year, semesters = self._calendar()
        scale = self._grading_scale()
        faculties, departments = self._structure(institution)
        programmes, versions = self._programmes(departments, year)
        self._courses(departments, versions)
        staff = self._staff(departments)
        sponsors = self._sponsors()
        self._students(programmes, versions, year, sponsors, student_count, staff.get("registrar"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
        self.stdout.write("")
        self.stdout.write(f"  Institution   {institution.name}")
        self.stdout.write(f"  Academic year {year.name} ({len(semesters)} semesters)")
        self.stdout.write(f"  Grading scale {scale.name} (max {scale.max_grade_point})")
        self.stdout.write(
            f"  Structure     {len(faculties)} faculties, {len(departments)} departments, "
            f"{len(programmes)} programmes, {Course.objects.count()} courses"
        )
        self.stdout.write(f"  Students      {student_count}")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Sign-in accounts"))
        self.stdout.write(f"  password for every account below: {DEMO_PASSWORD}")
        self.stdout.write("")
        for role in ROLES:
            email = f"{role.code}@demo.uniacmis.ss"
            if User.objects.filter(email=email).exists():
                self.stdout.write(f"  {role.code:<14} {email}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Every account is flagged must_change_password. Some students carry a "
                "stub fee hold, so /students/{id}/holds/ shows the blocked path."
            )
        )

    # ------------------------------------------------------------------ pieces

    def _institution(self) -> Institution:
        institution, _created = Institution.objects.get_or_create(
            name="University of Juba (demo)",
            defaults={
                "short_name": "UoJ Demo",
                "mohest_code": "SSD-UOJ-001",
                "address": "Juba, Central Equatoria, South Sudan",
                "phone": "+211920000000",
                "email": "registrar@demo.uniacmis.ss",
                "attendance_threshold_percent": Decimal("75.00"),
            },
        )
        return institution

    def _calendar(self) -> tuple[AcademicYear, list[Semester]]:
        year, _ = AcademicYear.objects.get_or_create(
            name="2026/2027",
            defaults={
                "start_date": date(2026, 9, 1),
                "end_date": date(2027, 7, 31),
                "is_current": not AcademicYear.objects.filter(is_current=True).exists(),
            },
        )

        specs = [
            (
                1,
                "Semester 1",
                date(2026, 9, 7),
                date(2026, 12, 18),
                date(2027, 1, 5),
                date(2027, 1, 23),
            ),
            (
                2,
                "Semester 2",
                date(2027, 2, 1),
                date(2027, 5, 21),
                date(2027, 6, 1),
                date(2027, 6, 19),
            ),
        ]

        semesters: list[Semester] = []
        for sequence, name, t_start, t_end, e_start, e_end in specs:
            semester, _ = Semester.objects.get_or_create(
                academic_year=year,
                sequence=sequence,
                defaults={
                    "name": name,
                    "teaching_start": t_start,
                    "teaching_end": t_end,
                    "exam_start": e_start,
                    "exam_end": e_end,
                    # Registration opens two weeks before teaching and add/drop runs
                    # two weeks into it — a realistic window, and open right now for
                    # semester 1 so the demo has something to show.
                    "registration_opens": _dt(t_start, -14),
                    "registration_closes": _dt(t_start, 7),
                    "add_drop_closes": _dt(t_start, 21),
                    "is_current": sequence == 1
                    and not Semester.objects.filter(is_current=True).exists(),
                },
            )
            semesters.append(semester)

        return year, semesters

    def _grading_scale(self) -> GradingScale:
        scale, created = GradingScale.objects.get_or_create(
            name="Standard 4.00 scale",
            defaults={
                "description": "Credit-weighted 4.00-point scale. Pass mark 50% (C).",
                "max_grade_point": Decimal("4.00"),
                "pass_grade_point": Decimal("2.00"),
                "is_default": not GradingScale.objects.filter(is_default=True).exists(),
            },
        )

        if created or not scale.bands.exists():
            for letter, low, high, points, is_pass, description in GRADE_BANDS:
                GradeBand.objects.get_or_create(
                    scale=scale,
                    letter=letter,
                    defaults={
                        "min_percent": Decimal(low),
                        "max_percent": Decimal(high),
                        "grade_point": Decimal(points),
                        "is_pass": is_pass,
                        "description": description,
                    },
                )
            # Fail loudly if the seeded scale does not actually cover 0–100.
            scale.validate_bands()

        return scale

    def _structure(
        self, institution: Institution
    ) -> tuple[dict[str, Faculty], dict[str, Department]]:
        faculties = {}
        for code, name in FACULTIES:
            faculty, _ = Faculty.objects.get_or_create(
                code=code, defaults={"name": name, "institution": institution}
            )
            faculties[code] = faculty

        departments = {}
        for code, name, faculty_code in DEPARTMENTS:
            department, _ = Department.objects.get_or_create(
                code=code, defaults={"name": name, "faculty": faculties[faculty_code]}
            )
            departments[code] = department

        return faculties, departments

    def _programmes(
        self, departments: dict[str, Department], year: AcademicYear
    ) -> tuple[dict[str, Programme], dict[str, CurriculumVersion]]:
        programmes = {}
        versions = {}

        for code, name, dept_code, award, duration, credits in PROGRAMMES:
            programme, _ = Programme.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "department": departments[dept_code],
                    "award": award,
                    "duration_years": duration,
                    "total_credits_required": credits,
                    "min_credits_per_semester": 12,
                    "max_credits_per_semester": 24,
                    "entry_requirements": {
                        "min_certificate_grade": "C",
                        "required_subjects": ["Mathematics", "English"],
                    },
                },
            )
            programmes[code] = programme

            version, _ = CurriculumVersion.objects.get_or_create(
                programme=programme,
                version="2026-v1",
                defaults={
                    "status": CurriculumStatus.ACTIVE,
                    "effective_from": year,
                    "notes": "Seeded demo curriculum.",
                },
            )
            versions[code] = version

        return programmes, versions

    def _courses(
        self, departments: dict[str, Department], versions: dict[str, CurriculumVersion]
    ) -> None:
        courses: dict[str, Course] = {}
        for code, title, dept_code, credits, level, _year, _sem in COURSES:
            course, _ = Course.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "department": departments[dept_code],
                    "credit_hours": credits,
                    "level": level,
                },
            )
            courses[code] = course

        for code, required_code, min_point in PREREQUISITES:
            Prerequisite.objects.get_or_create(
                course=courses[code],
                required_course=courses[required_code],
                defaults={
                    "minimum_grade_point": Decimal(min_point) if min_point else None,
                },
            )

        # Attach courses to each programme's curriculum: its own department's
        # courses plus the shared maths/statistics/general ones.
        shared = {"MTH101", "MTH102", "STA101", "GST101", "GST102"}
        prefix_for = {"CIV": "CVE", "ELE": "EEE", "BCS": "CSC", "STA": "STA"}

        for programme_code, version in versions.items():
            wanted = {
                code
                for code, *_rest in COURSES
                if code.startswith(prefix_for[programme_code]) or code in shared
            }
            if programme_code == "STA":
                wanted |= {"MTH201"}

            for code, _title, _dept, _credits, _level, year_of_study, semester in COURSES:
                if code not in wanted:
                    continue
                CurriculumCourse.objects.get_or_create(
                    curriculum_version=version,
                    course=courses[code],
                    defaults={
                        "year_of_study": year_of_study,
                        "semester_sequence": semester,
                        "is_core": True,
                    },
                )

    def _staff(self, departments: dict[str, Department]) -> dict[str, User]:
        created: dict[str, User] = {}
        counter = 1

        for role in ROLES:
            if role.code in {"student", "applicant"}:
                continue

            email = f"{role.code}@demo.uniacmis.ss"
            first, last, category, rank, dept_code = STAFF_ROLES.get(
                role.code,
                (
                    "Demo",
                    role.name,
                    StaffCategory.ADMINISTRATIVE,
                    AcademicRank.NOT_APPLICABLE,
                    None,
                ),
            )

            user, was_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "phone": f"+21192000{counter:04d}",
                    "is_active": True,
                    "must_change_password": True,
                    # ICT needs the Django admin, which is the working UI in Phase 1.
                    "is_staff": role.code == "ict_admin",
                    "is_superuser": role.code == "ict_admin",
                },
            )
            if was_created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])

            grant_role(user, role.code, reason="Seeded demo account")

            StaffProfile.objects.get_or_create(
                user=user,
                defaults={
                    "staff_number": f"STF/2026/{counter:04d}",
                    "department": departments.get(dept_code) if dept_code else None,
                    "staff_category": category,
                    "rank": rank,
                    "date_of_hire": date(2024, 1, 15),
                    "phone": user.phone,
                    "highest_qualification": "PhD" if rank == AcademicRank.PROFESSOR else "MSc",
                },
            )

            created[role.code] = user
            counter += 1

        # Head of department, so the HOD scoping rule has something to resolve.
        hod = created.get("hod")
        if hod is not None and hasattr(hod, "staff_profile"):
            csc = departments.get("CSC")
            if csc and csc.head_id is None:
                csc.head = hod.staff_profile
                csc.save(update_fields=["head"])

        return created

    def _sponsors(self) -> list[Sponsor]:
        specs = [
            ("Ministry of Higher Education Scholarship", SponsorType.GOVERNMENT),
            ("Nile Petroleum Foundation", SponsorType.COMPANY),
            ("Norwegian Refugee Council", SponsorType.NGO),
        ]
        sponsors = []
        for name, sponsor_type in specs:
            sponsor, _ = Sponsor.objects.get_or_create(
                name=name,
                defaults={"sponsor_type": sponsor_type, "contact_person": "Programme Officer"},
            )
            sponsors.append(sponsor)
        return sponsors

    def _students(
        self,
        programmes: dict[str, Programme],
        versions: dict[str, CurriculumVersion],
        year: AcademicYear,
        sponsors: list[Sponsor],
        count: int,
        actor: User | None,
    ) -> None:
        programme_codes = list(programmes)
        states = list(SouthSudanState.values)

        for index in range(count):
            gender = random.choice([Gender.FEMALE, Gender.MALE])
            first = random.choice(FIRST_NAMES_F if gender == Gender.FEMALE else FIRST_NAMES_M)
            middle = random.choice(MIDDLE_NAMES)
            last = random.choice(LAST_NAMES)

            programme_code = programme_codes[index % len(programme_codes)]
            sponsored = index % 4 == 0

            student = create_student(
                programme_id=programmes[programme_code].pk,
                entry_academic_year_id=year.pk,
                first_name=first,
                middle_name=middle,
                last_name=last,
                gender=gender,
                actor=actor,
                curriculum_version_id=versions[programme_code].pk,
                current_level=1,
                date_of_birth=date(2004 + (index % 4), 1 + (index % 12), 1 + (index % 27)),
                national_id_number=f"SSD{20260000 + index}",
                state_of_origin=states[index % len(states)],
                county=f"County {1 + (index % 8)}",
                has_disability=index % 15 == 0,
                disability_details="Requires seating near the front." if index % 15 == 0 else "",
                phone=f"+21192{1000000 + index}",
                email=f"student{index + 1}@demo.uniacmis.ss",
                sponsorship_type=(
                    SponsorshipType.GOVERNMENT if sponsored else SponsorshipType.SELF
                ),
                sponsor=random.choice(sponsors) if sponsored else None,
                reason="Seeded demo student",
            )

            NextOfKin.objects.create(
                student=student,
                full_name=f"{random.choice(FIRST_NAMES_M)} {last}",
                relationship="Parent",
                phone=f"+21192{2000000 + index}",
                is_primary=True,
            )


def _dt(day: date, offset_days: int):
    """Midday on `day + offset`, timezone-aware."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    naive = datetime.combine(day + timedelta(days=offset_days), time(12, 0))
    return timezone.make_aware(naive)
