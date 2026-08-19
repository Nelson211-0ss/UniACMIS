"""
Public service API for admissions.

Each function is one step of the lifecycle in checklist §3: inquiry → application
→ decision → conversion. Kept as explicit, separately-callable steps rather than
one big state machine method, because each step is authorised differently (an
applicant submits their own; a reviewer scores; a decision-maker decides; a
registrar converts) and each needs its own audit trail entry.
"""

from __future__ import annotations

import hashlib
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academics.services import calendar
from apps.admissions.eligibility import evaluate_entry_requirements
from apps.admissions.id_generation import generate_reference_number
from apps.admissions.merit_list import Candidate, generate_merit_list
from apps.admissions.models import (
    Application,
    ApplicationDocument,
    ApplicationFeePayment,
    ApplicationReview,
    ApplicationSource,
    ApplicationStatus,
    FeePaymentStatus,
)
from apps.core.exceptions import DomainError
from apps.core.ports import PaymentState
from apps.core.providers import get_notification_provider, get_payment_provider

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")

REQUIRED_TO_SUBMIT = ("first_name", "last_name", "gender", "phone")


class InvalidApplicationTransition(DomainError):
    code = "invalid_application_transition"
    message = "That action is not allowed for this application."


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ApplicationStatus.DRAFT: frozenset({ApplicationStatus.SUBMITTED, ApplicationStatus.WITHDRAWN}),
    ApplicationStatus.SUBMITTED: frozenset(
        {
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.OFFERED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.UNDER_REVIEW: frozenset(
        {ApplicationStatus.OFFERED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.OFFERED: frozenset(
        {ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.ACCEPTED: frozenset({ApplicationStatus.ENROLLED}),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.WITHDRAWN: frozenset(),
    ApplicationStatus.ENROLLED: frozenset(),
}


def _transition(application: Application, to_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(application.status, frozenset())
    if to_status not in allowed:
        raise InvalidApplicationTransition(
            f"Cannot move an application from {application.status} to {to_status}.",
            details={"from": application.status, "to": to_status, "allowed": sorted(allowed)},
        )


# ------------------------------------------------------------------- creation


@transaction.atomic
def create_application(
    *,
    programme_id: int,
    intended_academic_year_id: int,
    first_name: str,
    last_name: str,
    gender: str,
    source: str = ApplicationSource.SELF_SERVICE,
    applicant_user: Any | None = None,
    entered_by: Any | None = None,
    **extra: Any,
) -> Application:
    """FR-ADM-01 (self-service) and FR-ADM-02 (staff entry) — same function,
    distinguished by `source`. A reference number is allocated immediately so
    the applicant has something to quote even for a still-draft application.
    """
    year_name = calendar.academic_year_name(intended_academic_year_id)

    application = Application(
        reference_number=generate_reference_number(year_name),
        programme_id=programme_id,
        intended_academic_year_id=intended_academic_year_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        gender=gender,
        source=source,
        user=applicant_user,
        entered_by=entered_by,
        **extra,
    )
    application.audit_reason = f"Application created via {source}"
    application.full_clean()
    application.save()
    return application


def eligibility_warnings(application: Application) -> list[str]:
    """FR-ADM-03, surfaced to reviewers rather than enforced automatically."""
    return evaluate_entry_requirements(
        application.programme.entry_requirements, application.previous_grade
    )


@transaction.atomic
def submit_application(application: Application, *, reason: str = "") -> Application:
    """DRAFT → SUBMITTED. Requires the fee to be recorded (FR-ADM-04) and the
    bio-data a reviewer would need to actually consider the application."""
    _transition(application, ApplicationStatus.SUBMITTED)

    missing = [f for f in REQUIRED_TO_SUBMIT if not getattr(application, f)]
    if missing:
        raise ValidationError(dict.fromkeys(missing, "This field is required before submitting."))

    if not application.fee_paid:
        raise InvalidApplicationTransition(
            "The application fee must be paid and confirmed before submitting.",
            details={"reference_number": application.reference_number},
        )

    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = timezone.now()
    application.audit_reason = reason or "Submitted by applicant"
    application.full_clean()
    application.save()
    return application


@transaction.atomic
def withdraw_application(application: Application, *, reason: str) -> Application:
    if not reason.strip():
        raise InvalidApplicationTransition("A reason is required to withdraw an application.")
    _transition(application, ApplicationStatus.WITHDRAWN)
    application.status = ApplicationStatus.WITHDRAWN
    application.audit_reason = reason
    application.full_clean()
    application.save()
    return application


# --------------------------------------------------------------------- review


@transaction.atomic
def record_review(
    application: Application,
    *,
    reviewer: Any,
    score: Decimal,
    criteria: dict | None = None,
    comments: str = "",
) -> ApplicationReview:
    """FR-ADM-05. Upserts the reviewer's own row — a second look updates their
    score rather than adding a second vote — then recomputes the application's
    aggregate score and, on the first review, moves it into committee review."""
    review, _created = ApplicationReview.objects.update_or_create(
        application=application,
        reviewer=reviewer,
        defaults={"score": score, "criteria": criteria or {}, "comments": comments},
    )

    scores = list(application.reviews.values_list("score", flat=True))
    average = (
        (sum(scores) / len(scores)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if scores else None
    )

    application.score = average
    if application.status == ApplicationStatus.SUBMITTED:
        _transition(application, ApplicationStatus.UNDER_REVIEW)
        application.status = ApplicationStatus.UNDER_REVIEW
    application.audit_reason = f"Reviewed by {reviewer}"
    application.full_clean()
    application.save()
    return review


# ------------------------------------------------------------------- decision


@transaction.atomic
def decide_application(
    application: Application, decision: str, *, decided_by: Any, reason: str
) -> Application:
    """FR-ADM-05/07: offer or reject. Sends the applicant a notification
    through whichever provider is configured — console in development, the
    real SMS/email integration from Phase 6 in production, with no code here
    that changes when that swap happens."""
    if decision not in (ApplicationStatus.OFFERED, ApplicationStatus.REJECTED):
        raise InvalidApplicationTransition(f"'{decision}' is not a decision.")
    if not reason.strip():
        raise InvalidApplicationTransition("A reason is required for an admissions decision.")

    _transition(application, decision)
    application.status = decision
    application.reviewed_by = decided_by
    application.reviewed_at = timezone.now()
    application.decision_reason = reason
    application.audit_reason = reason
    application.full_clean()
    application.save()

    _notify_decision(application, decision)
    return application


def _notify_decision(application: Application, decision: str) -> None:
    provider = get_notification_provider()
    verb = "an offer of admission" if decision == ApplicationStatus.OFFERED else "a decision"
    body = (
        f"Dear {application.first_name}, your application {application.reference_number} "
        f"to {application.programme.name} has resulted in {verb}. "
        "Log in to the applicant portal for details."
    )
    try:
        if application.phone:
            provider.send_sms(application.phone, body, ref=application.reference_number)
        if application.email:
            provider.send_email(
                application.email,
                subject=f"Your application {application.reference_number}",
                body=body,
                ref=application.reference_number,
            )
    except Exception:  # pragma: no cover — a notification failure must not
        # roll back a real admissions decision.
        logger.exception("Failed to notify applicant %s of decision", application.reference_number)


@transaction.atomic
def accept_offer(application: Application, *, actor: Any | None = None) -> Application:
    """The applicant's own action — distinct from `decide_application`, which
    is staff deciding whether to make the offer at all."""
    _transition(application, ApplicationStatus.ACCEPTED)
    application.status = ApplicationStatus.ACCEPTED
    application.audit_reason = "Offer accepted by applicant"
    application.full_clean()
    application.save()
    return application


@transaction.atomic
def decline_offer(application: Application, *, reason: str = "") -> Application:
    _transition(application, ApplicationStatus.REJECTED)
    application.status = ApplicationStatus.REJECTED
    application.decision_reason = reason or "Declined by applicant"
    application.audit_reason = application.decision_reason
    application.full_clean()
    application.save()
    return application


# --------------------------------------------------------------- conversion


@transaction.atomic
def convert_to_student(application: Application, *, actor: Any | None = None):
    """FR-ADM-08: an accepted application becomes a student record with an
    auto-generated, non-reusable student ID — the same generator and the same
    guarantees as any other admission into `registry`."""
    from apps.registry.services import create_student

    _transition(application, ApplicationStatus.ENROLLED)

    if application.student_id:
        raise InvalidApplicationTransition("This application has already been converted.")

    student = create_student(
        programme_id=application.programme_id,
        entry_academic_year_id=application.intended_academic_year_id,
        first_name=application.first_name,
        middle_name=application.middle_name,
        last_name=application.last_name,
        gender=application.gender,
        actor=actor,
        national_id_number=application.national_id_number,
        nationality=application.nationality,
        state_of_origin=application.state_of_origin,
        county=application.county,
        has_disability=application.has_disability,
        disability_details=application.disability_details,
        phone=application.phone,
        email=application.email,
        physical_address=application.physical_address,
        previous_institution=application.previous_institution,
        previous_qualification=application.previous_qualification,
        date_of_birth=application.date_of_birth,
        user=application.user,
        reason=f"Converted from application {application.reference_number}",
    )

    application.status = ApplicationStatus.ENROLLED
    application.student = student
    application.audit_reason = f"Converted to student {student.student_id}"
    application.full_clean()
    application.save()
    return student


# ---------------------------------------------------------------- documents


def attach_document(
    *,
    application: Application,
    document_type: str,
    title: str,
    file: Any,
    uploaded_by: Any | None = None,
) -> ApplicationDocument:
    from django.conf import settings

    limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    size = getattr(file, "size", 0)
    if size > limit:
        raise ValidationError(
            {
                "file": f"This file is {size / 1024 / 1024:.1f} MB; the limit is {limit / 1024 / 1024:.0f} MB."
            }
        )

    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)

    return ApplicationDocument.objects.create(
        application=application,
        document_type=document_type,
        title=title,
        file=file,
        file_size=size,
        content_hash=digest.hexdigest(),
        uploaded_by=uploaded_by,
    )


# ------------------------------------------------------------------- payment


def initiate_fee_payment(
    application: Application, amount: Decimal, currency: str
) -> ApplicationFeePayment:
    provider = get_payment_provider()
    intent = provider.initiate(
        amount,
        currency,
        payer_ref=application.reference_number,
        invoice_ref=application.reference_number,
    )
    return ApplicationFeePayment.objects.create(
        application=application,
        provider=intent.provider,
        reference=intent.reference,
        amount=amount,
        currency=currency,
        status=FeePaymentStatus.PENDING,
    )


@transaction.atomic
def confirm_fee_payment(payment: ApplicationFeePayment) -> ApplicationFeePayment:
    """Polls the provider rather than assuming — a payment is only ever marked
    confirmed on the provider's own word (FR-ADM-04)."""
    provider = get_payment_provider()
    result = provider.status(payment.reference)

    if result.state == PaymentState.CONFIRMED:
        payment.status = FeePaymentStatus.CONFIRMED
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=["status", "confirmed_at"])
        Application.objects.filter(pk=payment.application_id).update(fee_paid=True)
    elif result.state == PaymentState.FAILED:
        payment.status = FeePaymentStatus.FAILED
        payment.save(update_fields=["status"])

    return payment


# --------------------------------------------------------------- merit list


def build_merit_list(programme_id: int, academic_year_id: int) -> list[dict[str, Any]]:
    """FR-ADM-06 over real applications: submitted-or-later applicants for one
    programme and intake year, ranked by score with configured quotas applied.
    """
    from apps.curriculum.services import admission_quota_rules

    quota_rules = admission_quota_rules(programme_id)
    queryset = Application.objects.filter(
        programme_id=programme_id,
        intended_academic_year_id=academic_year_id,
        status__in=[
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.OFFERED,
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
        ],
    )

    candidates = [
        Candidate(
            application_id=app.pk,
            score=app.score,
            attributes={
                "gender": app.gender,
                "state": app.state_of_origin,
                "disability": app.has_disability,
            },
        )
        for app in queryset
    ]

    entries = generate_merit_list(candidates, quota_rules or None)
    by_id = {app.pk: app for app in queryset}

    return [
        {
            "application_id": entry.application_id,
            "reference_number": by_id[entry.application_id].reference_number,
            "full_name": by_id[entry.application_id].get_full_name(),
            "rank": entry.rank,
            "score": entry.score,
            "admitted": entry.admitted,
            "quota_category": entry.quota_category,
        }
        for entry in entries
    ]
