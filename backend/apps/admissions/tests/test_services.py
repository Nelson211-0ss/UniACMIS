"""
Admissions service layer: the lifecycle from intake to conversion
(FR-ADM-01…08).
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.admissions import services
from apps.admissions.models import (
    Application,
    ApplicationFeePayment,
    ApplicationSource,
    ApplicationStatus,
    FeePaymentStatus,
)
from apps.admissions.services import InvalidApplicationTransition
from apps.core.providers import get_notification_provider, reset_provider_cache
from apps.registry.models import Gender

pytestmark = pytest.mark.django_db


@pytest.fixture
def recording_notifications(settings):
    settings.NOTIFICATION_PROVIDER = (
        "apps.core.providers.notifications.RecordingNotificationProvider"
    )
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture
def draft_application(programme, academic_year) -> Application:
    return services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="Achol",
        last_name="Malual",
        gender=Gender.FEMALE,
        phone="+211920000001",
        email="achol@example.ss",
    )


def _make_fee_paid(application: Application) -> None:
    application.fee_paid = True
    application.save(update_fields=["fee_paid"])


# ------------------------------------------------------------------- creation


def test_create_application_allocates_a_reference_number(draft_application):
    assert draft_application.reference_number.startswith("APP/")
    assert draft_application.status == ApplicationStatus.DRAFT


def test_reference_numbers_are_sequential_per_year(programme, academic_year):
    first = services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="A",
        last_name="One",
        gender=Gender.FEMALE,
    )
    second = services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="B",
        last_name="Two",
        gender=Gender.MALE,
    )
    assert first.reference_number != second.reference_number
    assert first.reference_number.endswith("00001")
    assert second.reference_number.endswith("00002")


def test_self_service_creation_defaults_the_source(draft_application):
    assert draft_application.source == ApplicationSource.SELF_SERVICE


def test_staff_entry_records_who_typed_it_in(programme, academic_year, registrar):
    application = services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="Walk",
        last_name="In",
        gender=Gender.MALE,
        source=ApplicationSource.STAFF_ENTRY,
        entered_by=registrar,
    )
    assert application.source == ApplicationSource.STAFF_ENTRY
    assert application.entered_by == registrar


def test_disability_requires_details(programme, academic_year):
    with pytest.raises(ValidationError):
        services.create_application(
            programme_id=programme.pk,
            intended_academic_year_id=academic_year.pk,
            first_name="A",
            last_name="B",
            gender=Gender.FEMALE,
            has_disability=True,
        )


# ------------------------------------------------------------------- eligibility


def test_eligibility_warnings_reads_the_programmes_own_requirements(draft_application, programme):
    programme.entry_requirements = {"min_certificate_grade": "B"}
    programme.save()
    draft_application.previous_grade = "D"
    draft_application.save()

    warnings = services.eligibility_warnings(draft_application)
    assert len(warnings) == 1


# -------------------------------------------------------------------- submit


def test_submit_requires_the_fee_to_be_paid(draft_application):
    with pytest.raises(InvalidApplicationTransition, match="fee must be paid"):
        services.submit_application(draft_application)


def test_submit_requires_the_core_bio_fields(programme, academic_year):
    application = services.create_application(
        programme_id=programme.pk,
        intended_academic_year_id=academic_year.pk,
        first_name="No",
        last_name="Phone",
        gender=Gender.FEMALE,
    )
    _make_fee_paid(application)
    with pytest.raises(ValidationError):
        services.submit_application(application)


def test_a_complete_paid_application_submits(draft_application):
    _make_fee_paid(draft_application)
    submitted = services.submit_application(draft_application)
    assert submitted.status == ApplicationStatus.SUBMITTED
    assert submitted.submitted_at is not None


def test_a_submitted_application_cannot_be_submitted_again(draft_application):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    with pytest.raises(InvalidApplicationTransition):
        services.submit_application(draft_application)


# ------------------------------------------------------------------ withdraw


def test_withdraw_requires_a_reason(draft_application):
    with pytest.raises(InvalidApplicationTransition, match="reason is required"):
        services.withdraw_application(draft_application, reason="")


def test_withdraw_from_draft(draft_application):
    withdrawn = services.withdraw_application(draft_application, reason="Changed my mind")
    assert withdrawn.status == ApplicationStatus.WITHDRAWN


def test_a_withdrawn_application_is_terminal(draft_application):
    services.withdraw_application(draft_application, reason="Changed my mind")
    with pytest.raises(InvalidApplicationTransition):
        services.withdraw_application(draft_application, reason="Changed my mind again")


# --------------------------------------------------------------------- review


def test_recording_a_review_moves_a_submitted_application_under_review(
    draft_application, registrar
):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)

    services.record_review(draft_application, reviewer=registrar, score=Decimal("75"))

    draft_application.refresh_from_db()
    assert draft_application.status == ApplicationStatus.UNDER_REVIEW
    assert draft_application.score == Decimal("75.00")


def test_a_second_review_from_a_different_reviewer_averages(
    draft_application, registrar, user_factory
):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    other = user_factory(email="reviewer2@test.ss")

    services.record_review(draft_application, reviewer=registrar, score=Decimal("80"))
    services.record_review(draft_application, reviewer=other, score=Decimal("60"))

    draft_application.refresh_from_db()
    assert draft_application.score == Decimal("70.00")
    assert draft_application.reviews.count() == 2


def test_the_same_reviewer_scoring_twice_updates_rather_than_duplicates(
    draft_application, registrar
):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)

    services.record_review(draft_application, reviewer=registrar, score=Decimal("50"))
    services.record_review(draft_application, reviewer=registrar, score=Decimal("90"))

    draft_application.refresh_from_db()
    assert draft_application.reviews.count() == 1
    assert draft_application.score == Decimal("90.00")


# ------------------------------------------------------------------- decision


def test_decide_requires_a_reason(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    with pytest.raises(InvalidApplicationTransition, match="reason is required"):
        services.decide_application(
            draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason=""
        )


def test_only_offer_or_reject_are_decisions(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    with pytest.raises(InvalidApplicationTransition, match="not a decision"):
        services.decide_application(
            draft_application, ApplicationStatus.WITHDRAWN, decided_by=registrar, reason="Nope"
        )


def test_an_offer_is_recorded_with_who_and_why(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    offered = services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Strong record"
    )
    assert offered.status == ApplicationStatus.OFFERED
    assert offered.reviewed_by == registrar
    assert offered.decision_reason == "Strong record"


def test_a_decision_notifies_the_applicant(draft_application, registrar, recording_notifications):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Strong record"
    )

    provider = get_notification_provider()
    assert len(provider.sent) == 2  # sms + email, both contact fields were set
    assert any(draft_application.reference_number in m["body"] for m in provider.sent)


def test_a_failed_notification_does_not_block_the_decision(
    draft_application, registrar, monkeypatch
):
    """The decision itself must survive a notification-provider failure —
    losing the SMS is not a reason to lose the admissions decision."""
    from apps.core.providers.notifications import ConsoleNotificationProvider

    def _boom(*args, **kwargs):
        raise ConnectionError("gateway unreachable")

    monkeypatch.setattr(ConsoleNotificationProvider, "send_sms", _boom)
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)

    offered = services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Strong record"
    )
    assert offered.status == ApplicationStatus.OFFERED


def test_accept_offer(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Strong record"
    )
    accepted = services.accept_offer(draft_application)
    assert accepted.status == ApplicationStatus.ACCEPTED


def test_decline_offer(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Strong record"
    )
    declined = services.decline_offer(draft_application, reason="Chose another university")
    assert declined.status == ApplicationStatus.REJECTED


def test_rejection_is_terminal(draft_application, registrar):
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    services.decide_application(
        draft_application, ApplicationStatus.REJECTED, decided_by=registrar, reason="Below minimum"
    )
    with pytest.raises(InvalidApplicationTransition):
        services.decide_application(
            draft_application,
            ApplicationStatus.OFFERED,
            decided_by=registrar,
            reason="Reconsidered",
        )


# ----------------------------------------------------------------- conversion


def _accepted_application(draft_application, registrar) -> Application:
    _make_fee_paid(draft_application)
    services.submit_application(draft_application)
    services.decide_application(
        draft_application, ApplicationStatus.OFFERED, decided_by=registrar, reason="Meets criteria"
    )
    return services.accept_offer(draft_application)


def test_convert_requires_an_accepted_offer(draft_application, registrar):
    with pytest.raises(InvalidApplicationTransition):
        services.convert_to_student(draft_application, actor=registrar)


def test_converting_an_accepted_application_creates_a_student(draft_application, registrar):
    application = _accepted_application(draft_application, registrar)

    student = services.convert_to_student(application, actor=registrar)

    application.refresh_from_db()
    assert application.status == ApplicationStatus.ENROLLED
    assert application.student_id == student.pk
    assert student.get_full_name() == application.get_full_name()
    assert student.programme_id == application.programme_id


def test_converting_twice_is_refused(draft_application, registrar):
    application = _accepted_application(draft_application, registrar)
    services.convert_to_student(application, actor=registrar)
    with pytest.raises(InvalidApplicationTransition):
        services.convert_to_student(application, actor=registrar)


# -------------------------------------------------------------------- payments


def test_initiate_fee_payment_creates_a_pending_record(draft_application):
    payment = services.initiate_fee_payment(draft_application, Decimal("15000"), "SSP")
    assert payment.status == FeePaymentStatus.PENDING
    assert payment.reference.startswith("MOCK-")


def test_confirming_a_payment_needs_two_provider_polls(draft_application):
    """Matches the Phase 1 MockPaymentProvider's documented behaviour: it
    confirms on the second status() poll, so callers must handle "still
    pending" rather than assuming instant settlement."""
    payment = services.initiate_fee_payment(draft_application, Decimal("15000"), "SSP")

    first = services.confirm_fee_payment(payment)
    assert first.status == FeePaymentStatus.PENDING
    draft_application.refresh_from_db()
    assert draft_application.fee_paid is False

    second = services.confirm_fee_payment(payment)
    assert second.status == FeePaymentStatus.CONFIRMED
    assert second.confirmed_at is not None

    draft_application.refresh_from_db()
    assert draft_application.fee_paid is True


def test_confirming_an_unknown_reference_fails_without_touching_the_application(draft_application):
    payment = ApplicationFeePayment.objects.create(
        application=draft_application,
        provider="mock",
        reference="MOCK-DOES-NOT-EXIST",
        amount=Decimal("100"),
        currency="SSP",
    )
    result = services.confirm_fee_payment(payment)
    assert result.status == FeePaymentStatus.FAILED
    draft_application.refresh_from_db()
    assert draft_application.fee_paid is False


# ------------------------------------------------------------------ documents


def test_attach_document_hashes_the_content(draft_application):
    upload = SimpleUploadedFile("cert.pdf", b"certificate-bytes", content_type="application/pdf")
    document = services.attach_document(
        application=draft_application, document_type="certificate", title="Certificate", file=upload
    )
    assert document.content_hash
    assert document.file_size == len(b"certificate-bytes")


def test_attach_document_rejects_an_oversized_file(draft_application, settings):
    settings.MAX_UPLOAD_SIZE_MB = 1
    big = SimpleUploadedFile("big.pdf", io.BytesIO(b"0" * (2 * 1024 * 1024)).read())
    with pytest.raises(ValidationError):
        services.attach_document(
            application=draft_application, document_type="certificate", title="Too big", file=big
        )
