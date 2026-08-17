"""
The audit trail (FR-RPT-04, NFR-SEC-03).

Two things are being asserted: that changes are captured with their old and new
values, and that the record cannot be rewritten afterwards without detection.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest
from django.db import IntegrityError, connection

from apps.audit.models import GENESIS_HASH, AuditAction, AuditLog
from apps.audit.services import canonical_payload, compute_row_hash, record_action, verify_chain
from apps.core import context
from apps.registry.models import StudentStatus

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ capture


def test_creating_an_audited_model_records_a_create_entry(institution):
    entries = AuditLog.objects.for_object(institution)
    assert entries.filter(action=AuditAction.CREATE).exists()


def test_changing_a_tracked_field_records_old_and_new_values(institution):
    institution.mohest_code = "SSD-TU-999"
    institution.save()

    entry = AuditLog.objects.for_object(institution).filter(field_name="mohest_code").first()
    assert entry is not None
    assert entry.old_value == "SSD-TU-001"
    assert entry.new_value == "SSD-TU-999"
    assert entry.action == AuditAction.UPDATE


def test_untracked_fields_do_not_generate_entries(institution):
    before = AuditLog.objects.count()
    institution.website = "https://example.ss"  # not in audit_fields
    institution.save()
    assert AuditLog.objects.count() == before


def test_one_entry_per_changed_field(institution):
    before = AuditLog.objects.count()
    institution.name = "Renamed University"
    institution.mohest_code = "SSD-TU-777"
    institution.save()
    assert AuditLog.objects.count() == before + 2


def test_no_entry_when_a_tracked_field_is_saved_unchanged(institution):
    before = AuditLog.objects.count()
    institution.save()
    assert AuditLog.objects.count() == before


def test_reason_is_captured(student):
    from apps.registry import services

    services.change_status(
        student,
        StudentStatus.SUSPENDED,
        reason="Disciplinary hearing pending — Senate minute 14/2026",
        effective_date=None,
    )

    entry = AuditLog.objects.for_object(student).filter(field_name="status").first()
    assert entry is not None
    assert "Senate minute 14/2026" in entry.reason


def test_actor_is_snapshotted_and_survives_user_deletion(institution, registrar):
    with context.acting_as(registrar):
        institution.mohest_code = "SSD-TU-555"
        institution.save()

    entry = AuditLog.objects.for_object(institution).filter(field_name="mohest_code").first()
    assert entry is not None
    assert entry.actor_name == registrar.get_full_name()
    assert entry.actor_role == "registrar"

    registrar.delete()
    entry.refresh_from_db()
    # The FK is nulled, but the trail still says who did it.
    assert entry.actor_id is None
    assert entry.actor_name != ""


def test_unattributed_changes_are_recorded_as_system(institution):
    institution.mohest_code = "SSD-TU-000"
    institution.save()

    entry = AuditLog.objects.for_object(institution).filter(field_name="mohest_code").first()
    assert entry is not None
    assert entry.actor_name == context.SYSTEM_ACTOR_NAME


def test_deleting_an_audited_model_records_it(faculty):
    faculty.delete()
    assert AuditLog.objects.filter(action=AuditAction.DELETE, object_repr__icontains="ENG").exists()


# --------------------------------------------------------------- append-only


def test_an_entry_cannot_be_re_saved(institution):
    entry = AuditLog.objects.first()
    assert entry is not None
    with pytest.raises(IntegrityError, match="append-only"):
        entry.save()


def test_an_entry_cannot_be_deleted(institution):
    entry = AuditLog.objects.first()
    assert entry is not None
    with pytest.raises(IntegrityError, match="cannot be deleted"):
        entry.delete()


def test_the_queryset_cannot_be_deleted(institution):
    with pytest.raises(IntegrityError, match="append-only"):
        AuditLog.objects.all().delete()


def test_the_queryset_cannot_be_updated(institution):
    with pytest.raises(IntegrityError, match="append-only"):
        AuditLog.objects.all().update(reason="rewritten")


# -------------------------------------------------------------- hash chain


@pytest.fixture
def several_entries(institution):
    """A handful of entries, so chain assertions have a real chain to walk."""
    for index in range(4):
        institution.mohest_code = f"SSD-TU-{index:03d}"
        institution.save()
    assert AuditLog.objects.count() >= 5
    return institution


def test_chain_starts_from_genesis_and_links_forward(several_entries):
    entries = list(AuditLog.objects.order_by("id"))
    assert len(entries) >= 2
    assert entries[0].prev_hash == GENESIS_HASH

    for previous, current in pairwise(entries):
        assert current.prev_hash == previous.row_hash


def test_each_row_hash_matches_its_own_contents(institution):
    for entry in AuditLog.objects.all():
        assert entry.row_hash == compute_row_hash(entry.prev_hash, canonical_payload(entry))


def test_verify_chain_reports_intact(institution):
    result = verify_chain()
    assert result["ok"] is True
    assert result["checked"] == AuditLog.objects.count()
    assert result["first_broken_id"] is None


def test_verify_chain_detects_an_edited_entry(institution):
    """The point of the chain: editing history is detectable even by someone with
    direct database access, who can bypass every application-level guard."""
    target = AuditLog.objects.order_by("id").first()
    assert target is not None

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE audit_auditlog SET new_value = %s WHERE id = %s",
            ["tampered", target.id],
        )

    result = verify_chain()
    assert result["ok"] is False
    assert result["first_broken_id"] == target.id
    assert "altered" in result["detail"]


def test_verify_chain_detects_a_deleted_entry(several_entries):
    entries = list(AuditLog.objects.order_by("id"))
    assert len(entries) >= 3
    victim = entries[1]

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [victim.id])

    result = verify_chain()
    assert result["ok"] is False
    # The break shows up at the entry that followed the removed one.
    assert result["first_broken_id"] == entries[2].id
    assert "removed or altered" in result["detail"]


def test_chain_remains_valid_across_many_writes(institution):
    for index in range(15):
        institution.mohest_code = f"SSD-TU-{index:03d}"
        institution.save()

    assert verify_chain()["ok"] is True


def test_record_action_without_an_instance(db):
    """Failed sign-ins have no target object but must still be recorded."""
    record_action(instance=None, action=AuditAction.LOGIN_FAILED, description="unknown address")
    entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).first()
    assert entry is not None
    assert entry.content_type_id is None
    assert verify_chain()["ok"] is True


def test_verify_chain_on_empty_log(db):
    result = verify_chain()
    assert result["ok"] is True
    assert result["checked"] == 0


# ------------------------------------------------- money values in the trail


def test_decimal_values_are_stored_readably(grading_scale):
    grading_scale.pass_grade_point = Decimal("2.50")
    grading_scale.save()

    entry = AuditLog.objects.for_object(grading_scale).filter(field_name="pass_grade_point").first()
    assert entry is not None
    assert entry.old_value == "2.00"
    assert entry.new_value == "2.50"
