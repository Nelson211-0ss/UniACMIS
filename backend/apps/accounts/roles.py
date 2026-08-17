"""
The authorisation policy, in one file.

Roles come from SRS §2.2. Each lists the permissions it holds, so "what may a
bursar do?" is answerable by reading one diff rather than by grepping views.
`manage.py seed_roles` applies this to the database idempotently, which makes a
policy change a data operation rather than a code change.

Permissions for modules that do not exist yet (finance, examinations, library …)
are listed here deliberately: this file is the *policy*, and the policy is decided
now. `seed_roles` skips any permission whose model is not installed and reports it
as pending, so the list stays honest as the phases land.

Separation of duties (NFR-SEC-01) is asserted by a test, not by convention:
no role may hold both grade-write and money-write permissions, and `ict_admin`
holds neither — an ICT officer who wants them has to grant themselves a role,
which the audit trail records.
"""

from __future__ import annotations

from dataclasses import dataclass


def crud(model: str) -> tuple[str, ...]:
    """add/change/delete/view for `app_label.modelname`."""
    app_label, model_name = model.split(".")
    return tuple(f"{app_label}.{verb}_{model_name}" for verb in ("add", "change", "delete", "view"))


def write(model: str) -> tuple[str, ...]:
    """add/change/view — no delete. The default for academic and financial
    records, which are corrected by a further entry, never removed."""
    app_label, model_name = model.split(".")
    return tuple(f"{app_label}.{verb}_{model_name}" for verb in ("add", "change", "view"))


def ro(model: str) -> tuple[str, ...]:
    app_label, model_name = model.split(".")
    return (f"{app_label}.view_{model_name}",)


@dataclass(frozen=True)
class RoleDefinition:
    code: str
    name: str
    description: str
    permissions: tuple[str, ...]


# --------------------------------------------------------------- permission sets

CURRICULUM_READ = (
    *ro("curriculum.faculty"),
    *ro("curriculum.department"),
    *ro("curriculum.programme"),
    *ro("curriculum.course"),
    *ro("curriculum.curriculumversion"),
    *ro("curriculum.curriculumcourse"),
    *ro("curriculum.prerequisite"),
)

CURRICULUM_MANAGE = (
    *crud("curriculum.faculty"),
    *crud("curriculum.department"),
    *crud("curriculum.programme"),
    *crud("curriculum.course"),
    *write("curriculum.curriculumversion"),
    *crud("curriculum.curriculumcourse"),
    *crud("curriculum.prerequisite"),
)

ACADEMICS_READ = (
    *ro("academics.institution"),
    *ro("academics.academicyear"),
    *ro("academics.semester"),
    *ro("academics.gradingscale"),
    *ro("academics.gradeband"),
)

ACADEMICS_MANAGE = (
    *write("academics.institution"),
    *write("academics.academicyear"),
    *write("academics.semester"),
    *write("academics.gradingscale"),
    *write("academics.gradeband"),
)

REGISTRY_MANAGE = (
    *write("registry.student"),
    *ro("registry.studentstatushistory"),
    "registry.change_student_status",
    *crud("registry.nextofkin"),
    *crud("registry.sponsor"),
    *write("registry.studentdocument"),
    "registry.verify_studentdocument",
)

# Written now so the rule they encode is testable in Phase 1, even though the
# modules land later.
GRADE_WRITE_PERMISSIONS = frozenset(
    {
        "examinations.add_mark",
        "examinations.change_mark",
        "examinations.add_assessment",
        "examinations.change_assessment",
        "examinations.moderate_result",
        "examinations.approve_result",
    }
)

MONEY_WRITE_PERMISSIONS = frozenset(
    {
        "finance.add_payment",
        "finance.change_payment",
        "finance.add_invoice",
        "finance.change_invoice",
        "finance.add_feestructure",
        "finance.change_feestructure",
        "finance.approve_refund",
    }
)


# ------------------------------------------------------------------------ roles

ROLES: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        code="applicant",
        name="Applicant",
        description="Prospective student. Can apply and track their own application.",
        # Everything an applicant may see is their own record, enforced by
        # queryset scoping in Phase 2 rather than by a broad permission here.
        permissions=(),
    ),
    RoleDefinition(
        code="student",
        name="Student",
        description=(
            "Registered student. Sees their own record, registration, results, "
            "invoices and documents — narrowed by queryset scoping."
        ),
        permissions=(
            *ro("registry.student"),
            *ro("registry.studentdocument"),
            *CURRICULUM_READ,
            *ACADEMICS_READ,
        ),
    ),
    RoleDefinition(
        code="lecturer",
        name="Lecturer",
        description=(
            "Teaches courses. Marks attendance and enters assessment scores for "
            "their own allocated courses only."
        ),
        permissions=(
            *ro("registry.student"),
            *CURRICULUM_READ,
            *ACADEMICS_READ,
            # Phase 3
            "attendance.add_sessionrecord",
            "attendance.change_sessionrecord",
            "attendance.view_sessionrecord",
            "examinations.add_mark",
            "examinations.change_mark",
            "examinations.view_mark",
        ),
    ),
    RoleDefinition(
        code="hod",
        name="Head of Department",
        description=(
            "Runs a department: approves course allocations, monitors performance, "
            "moderates marks within the department."
        ),
        permissions=(
            *ro("registry.student"),
            *ro("registry.staffprofile"),
            *CURRICULUM_READ,
            *ACADEMICS_READ,
            "curriculum.change_curriculumcourse",
            # Phase 3
            "attendance.view_sessionrecord",
            "examinations.view_mark",
            "examinations.moderate_result",
            "timetabling.view_timetableentry",
        ),
    ),
    RoleDefinition(
        code="registrar",
        name="Registrar",
        description=(
            "Owns admissions, enrollment, student records, transcripts and " "graduation clearance."
        ),
        permissions=(
            *REGISTRY_MANAGE,
            *CURRICULUM_MANAGE,
            *ACADEMICS_READ,
            *ro("registry.staffprofile"),
            *ro("core.syncoperation"),
            *ro("core.syncconflict"),
            # Phase 2 onward
            "admissions.view_application",
            "admissions.change_application",
            "admissions.decide_application",
            "enrollment.add_courseregistration",
            "enrollment.change_courseregistration",
            "enrollment.view_courseregistration",
            "enrollment.override_hold",
            "documents.add_transcriptrequest",
            "documents.change_transcriptrequest",
            "documents.issue_certificate",
        ),
    ),
    RoleDefinition(
        code="finance",
        name="Finance / Bursar",
        description=(
            "Fee structures, invoicing, receipting, reconciliation and "
            "scholarships. No access to marks."
        ),
        permissions=(
            *ro("registry.student"),
            *ro("registry.sponsor"),
            *ro("curriculum.programme"),
            *ACADEMICS_READ,
            # Phase 4
            "finance.add_feestructure",
            "finance.change_feestructure",
            "finance.view_feestructure",
            "finance.add_invoice",
            "finance.change_invoice",
            "finance.view_invoice",
            "finance.add_payment",
            "finance.change_payment",
            "finance.view_payment",
            "finance.view_scholarship",
            "finance.change_scholarship",
            "finance.approve_refund",
            "finance.view_defaulterreport",
        ),
    ),
    RoleDefinition(
        code="examinations",
        name="Examinations Office",
        description=(
            "Exam scheduling, results processing, moderation and Senate submission. "
            "No access to fee records."
        ),
        permissions=(
            *ro("registry.student"),
            *CURRICULUM_READ,
            *ACADEMICS_MANAGE,
            # Phase 3
            "examinations.add_assessment",
            "examinations.change_assessment",
            "examinations.view_assessment",
            "examinations.view_mark",
            "examinations.change_mark",
            "examinations.moderate_result",
            "examinations.publish_result",
            "timetabling.add_examtimetable",
            "timetabling.change_examtimetable",
            "timetabling.view_examtimetable",
        ),
    ),
    RoleDefinition(
        code="senate",
        name="Senate / Exam Board",
        description=(
            "Approves results before publication (FR-EXM-05). Approval is a "
            "distinct permission from processing them, so the office that "
            "prepares results cannot also approve them."
        ),
        permissions=(
            *ro("registry.student"),
            *ACADEMICS_READ,
            "examinations.view_mark",
            "examinations.view_assessment",
            "examinations.approve_result",
        ),
    ),
    RoleDefinition(
        code="hr",
        name="Human Resources",
        description="Staff records, contracts, leave, appraisal and payroll export.",
        permissions=(
            *crud("registry.staffprofile"),
            *ro("curriculum.department"),
            *ro("curriculum.faculty"),
            # Phase 5
            "hr.add_contract",
            "hr.change_contract",
            "hr.view_contract",
            "hr.add_leaverequest",
            "hr.change_leaverequest",
            "hr.view_leaverequest",
            "hr.approve_leaverequest",
            "hr.view_appraisal",
            "hr.change_appraisal",
            "hr.export_payroll",
        ),
    ),
    RoleDefinition(
        code="library",
        name="Library Staff",
        description="Catalogue and circulation, including offline desk circulation.",
        permissions=(
            *ro("registry.student"),
            *ro("registry.staffprofile"),
            # Phase 5
            "library.add_libraryitem",
            "library.change_libraryitem",
            "library.view_libraryitem",
            "library.add_loan",
            "library.change_loan",
            "library.view_loan",
            "library.waive_fine",
        ),
    ),
    RoleDefinition(
        code="hostel",
        name="Hostel Office",
        description="Room inventory, allocation and occupancy.",
        permissions=(
            *ro("registry.student"),
            # Phase 5
            "hostel.add_room",
            "hostel.change_room",
            "hostel.view_room",
            "hostel.add_allocation",
            "hostel.change_allocation",
            "hostel.view_allocation",
        ),
    ),
    RoleDefinition(
        code="ict_admin",
        name="ICT Administrator",
        description=(
            "User accounts, permissions, sync operations, backups and the audit "
            "trail. Deliberately holds no grade-write or money-write permission: "
            "granting themselves one requires a role change, which is audited."
        ),
        permissions=(
            *crud("accounts.user"),
            *ro("accounts.role"),
            *crud("accounts.userrole"),
            *ro("audit.auditlog"),
            *ro("core.syncoperation"),
            *ro("core.syncconflict"),
            "core.resolve_syncconflict",
            *ro("core.idsequence"),
            *ACADEMICS_READ,
            *CURRICULUM_READ,
            *ro("registry.student"),
            *ro("registry.staffprofile"),
        ),
    ),
    RoleDefinition(
        code="management",
        name="University Management",
        description="Dashboards, KPIs and statutory reports. Read-only throughout.",
        permissions=(
            *ro("registry.student"),
            *ro("registry.staffprofile"),
            *CURRICULUM_READ,
            *ACADEMICS_READ,
            *ro("audit.auditlog"),
            # Phase 6
            "reporting.view_dashboard",
            "reporting.export_statutoryreport",
        ),
    ),
)

ROLES_BY_CODE: dict[str, RoleDefinition] = {role.code: role for role in ROLES}
ROLE_CODES: tuple[str, ...] = tuple(role.code for role in ROLES)


def permissions_for(code: str) -> frozenset[str]:
    definition = ROLES_BY_CODE.get(code)
    return frozenset(definition.permissions) if definition else frozenset()
