"""
Offline sync (NFR-AVAIL-01).

The scenario throughout: a registry clerk types admission forms during an outage
and the queue flushes when the link returns. What must never happen is a duplicate
student, a silently overwritten value, or one bad row taking down the batch.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.exceptions import SyncConflictDetected
from apps.core.models import (
    ConflictPolicy,
    ConflictResolution,
    SyncConflict,
    SyncOperation,
    SyncStatus,
)
from apps.core.sync.engine import apply_batch, apply_operation
from apps.core.sync.handlers import (
    SyncOperationInput,
    get_handler,
    register_handler,
    registered_entities,
)
from apps.registry.models import Gender, Student

pytestmark = pytest.mark.django_db

BATCH_URL = "/api/v1/sync/batch/"
SINGLE_URL = "/api/v1/sync/operations/"


def _student_payload(**overrides):
    payload = {
        "first_name": "Achol",
        "last_name": "Malual",
        "gender": Gender.FEMALE,
    }
    payload.update(overrides)
    return payload


def _op(programme, year, **overrides) -> dict:
    op = {
        "client_op_id": str(uuid.uuid4()),
        "entity": "registry.student",
        "action": "create",
        "payload": _student_payload(
            programme_id=programme.pk, entry_academic_year_id=year.pk, **overrides
        ),
        "client_timestamp": timezone.now().isoformat(),
        "device_id": "registry-laptop-02",
    }
    return op


# --------------------------------------------------------------- registration


def test_the_student_handler_is_registered():
    assert get_handler("registry.student") is not None


def test_registered_entities_expose_their_conflict_policy():
    assert registered_entities()["registry.student"] in ConflictPolicy.values


def test_a_handler_missing_required_attributes_is_refused():
    class Incomplete:
        entity = "bad.entity"

    with pytest.raises(TypeError, match="missing"):
        register_handler(Incomplete)


def test_a_handler_with_an_unknown_conflict_policy_is_refused():
    class BadPolicy:
        entity = "bad.policy"
        actions = ("create",)
        conflict_policy = "hope_for_the_best"
        required_permission = "registry.add_student"

        def apply(self, op, actor):  # pragma: no cover
            return {}

    with pytest.raises(TypeError, match="unknown conflict policy"):
        register_handler(BadPolicy)


# ------------------------------------------------------------------ the engine


@pytest.mark.integration
def test_a_queued_operation_creates_the_record(
    registrar, programme, academic_year, institution, as_user
):
    client = as_user(registrar)
    operation = _op(programme, academic_year)

    response = client.post(BATCH_URL, {"operations": [operation]}, format="json")

    assert response.status_code == 200
    result = response.data["results"][0]
    assert result["status"] == SyncStatus.APPLIED
    assert result["result"]["student_id"].startswith("ENG/CIV/2026/")
    assert Student.objects.filter(pk=result["result"]["id"]).exists()


@pytest.mark.integration
def test_replaying_a_batch_creates_nothing_new(
    registrar, programme, academic_year, institution, as_user
):
    """The behaviour the whole design turns on: the client retries the batch after
    a dropped connection, and the retry is a no-op."""
    client = as_user(registrar)
    operations = [_op(programme, academic_year) for _ in range(3)]

    first = client.post(BATCH_URL, {"operations": operations}, format="json")
    assert first.data["summary"] == {SyncStatus.APPLIED: 3}
    created = Student.objects.count()

    second = client.post(BATCH_URL, {"operations": operations}, format="json")

    assert second.data["summary"] == {SyncStatus.DUPLICATE: 3}
    assert Student.objects.count() == created


@pytest.mark.integration
def test_a_replay_returns_the_original_result(
    registrar, programme, academic_year, institution, as_user
):
    """So the client can reconcile its queue: it learns the student ID that was
    issued the first time, not just that the row was a duplicate."""
    client = as_user(registrar)
    operation = _op(programme, academic_year)

    first = client.post(BATCH_URL, {"operations": [operation]}, format="json")
    original = first.data["results"][0]["result"]

    second = client.post(BATCH_URL, {"operations": [operation]}, format="json")
    replayed = second.data["results"][0]

    assert replayed["status"] == SyncStatus.DUPLICATE
    assert replayed["result"]["student_id"] == original["student_id"]


@pytest.mark.integration
def test_one_bad_operation_does_not_sink_the_batch(
    registrar, programme, academic_year, institution, as_user
):
    """Ninety good attendance rows must land even when the ninety-first is
    malformed."""
    client = as_user(registrar)
    good_one = _op(programme, academic_year)
    bad = _op(programme, academic_year)
    bad["payload"].pop("first_name")
    good_two = _op(programme, academic_year)

    response = client.post(BATCH_URL, {"operations": [good_one, bad, good_two]}, format="json")

    statuses = [r["status"] for r in response.data["results"]]
    assert statuses == [SyncStatus.APPLIED, SyncStatus.REJECTED, SyncStatus.APPLIED]
    assert Student.objects.count() == 2
    assert response.data["results"][1]["error"]["code"] == "validation_error"


@pytest.mark.integration
def test_an_unknown_entity_is_rejected_not_ignored(registrar, as_user):
    client = as_user(registrar)
    response = client.post(
        BATCH_URL,
        {
            "operations": [
                {
                    "client_op_id": str(uuid.uuid4()),
                    "entity": "attendance.session_record",  # arrives in Phase 3
                    "action": "create",
                    "payload": {},
                }
            ]
        },
        format="json",
    )

    result = response.data["results"][0]
    assert result["status"] == SyncStatus.REJECTED
    assert result["error"]["code"] == "unknown_entity"


@pytest.mark.integration
def test_an_unsupported_action_is_rejected(registrar, programme, academic_year, as_user):
    client = as_user(registrar)
    operation = _op(programme, academic_year)
    operation["action"] = "delete"

    response = client.post(BATCH_URL, {"operations": [operation]}, format="json")
    assert response.data["results"][0]["error"]["code"] == "unsupported_action"


@pytest.mark.integration
def test_permissions_are_enforced_per_operation(
    roles, staff_factory, programme, academic_year, institution, as_user
):
    """A lecturer may sync attendance but not create students."""
    lecturer = staff_factory("lecturer", email="lect@sync.test")
    client = as_user(lecturer)

    response = client.post(
        BATCH_URL, {"operations": [_op(programme, academic_year)]}, format="json"
    )

    result = response.data["results"][0]
    assert result["status"] == SyncStatus.REJECTED
    assert result["error"]["code"] == "permission_denied"
    assert Student.objects.count() == 0


@pytest.mark.integration
def test_a_duplicate_id_within_one_batch_is_refused_up_front(
    registrar, programme, academic_year, as_user
):
    client = as_user(registrar)
    operation = _op(programme, academic_year)

    response = client.post(BATCH_URL, {"operations": [operation, dict(operation)]}, format="json")
    assert response.status_code == 400
    assert "Duplicate client_op_id" in str(response.data)


@pytest.mark.integration
def test_an_empty_batch_is_refused(registrar, as_user):
    response = as_user(registrar).post(BATCH_URL, {"operations": []}, format="json")
    assert response.status_code == 400


@pytest.mark.integration
def test_an_oversized_batch_is_refused(registrar, programme, academic_year, as_user):
    """A device offline for a week flushes in several requests rather than one
    that times out on a 2G link and gets retried from scratch."""
    client = as_user(registrar)
    operations = [_op(programme, academic_year) for _ in range(201)]

    response = client.post(BATCH_URL, {"operations": operations}, format="json")
    assert response.status_code == 400
    assert "at most 200" in str(response.data)


# ------------------------------------------------------------------ conflicts


@pytest.mark.integration
def test_the_same_person_queued_twice_is_flagged_not_duplicated(
    registrar, programme, academic_year, institution, as_user
):
    """Two different operation ids for one human — the clerk retyped the form
    after the app appeared to lose it. Idempotency cannot catch this, so the
    handler does.
    """
    client = as_user(registrar)

    first = _op(programme, academic_year, national_id_number="SSD12345678")
    client.post(BATCH_URL, {"operations": [first]}, format="json")

    again = _op(programme, academic_year, national_id_number="SSD12345678")
    response = client.post(BATCH_URL, {"operations": [again]}, format="json")

    result = response.data["results"][0]
    assert result["status"] == SyncStatus.CONFLICT
    assert Student.objects.count() == 1

    conflict = SyncConflict.objects.get(pk=result["conflict_id"])
    assert conflict.field_name == "national_id_number"
    assert conflict.status == ConflictResolution.OPEN
    assert "already exists" in conflict.sync_operation.error_detail


@pytest.mark.integration
def test_a_conflict_holds_both_values_for_review(
    registrar, programme, academic_year, institution, as_user
):
    client = as_user(registrar)
    client.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD999")]},
        format="json",
    )
    response = client.post(
        BATCH_URL,
        {
            "operations": [
                _op(
                    programme,
                    academic_year,
                    national_id_number="SSD999",
                    first_name="Different",
                    last_name="Person",
                )
            ]
        },
        format="json",
    )

    conflict = SyncConflict.objects.get(pk=response.data["results"][0]["conflict_id"])
    assert conflict.server_value  # the record already on file
    assert "Different Person" in conflict.client_value


@pytest.mark.integration
def test_a_conflict_appears_in_the_open_list(
    registrar, programme, academic_year, institution, as_user
):
    client = as_user(registrar)
    client.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD777")]},
        format="json",
    )
    client.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD777")]},
        format="json",
    )

    listing = client.get("/api/v1/sync/conflicts/")
    assert listing.status_code == 200
    assert listing.data["count"] == 1


@pytest.mark.integration
def test_resolving_a_conflict_requires_a_reason(
    ict_admin, registrar, programme, academic_year, institution, as_user
):
    clerk = as_user(registrar)
    clerk.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD555")]},
        format="json",
    )
    response = clerk.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD555")]},
        format="json",
    )
    conflict_id = response.data["results"][0]["conflict_id"]

    admin = as_user(ict_admin)
    url = f"/api/v1/sync/conflicts/{conflict_id}/resolve/"

    without_reason = admin.post(
        url, {"resolution": ConflictResolution.RESOLVED_SERVER}, format="json"
    )
    assert without_reason.status_code == 400

    with_reason = admin.post(
        url,
        {
            "resolution": ConflictResolution.RESOLVED_SERVER,
            "reason": "Confirmed with the applicant — same person, keep the first record.",
        },
        format="json",
    )
    assert with_reason.status_code == 200
    assert with_reason.data["status"] == ConflictResolution.RESOLVED_SERVER


@pytest.mark.integration
def test_a_resolved_conflict_cannot_be_resolved_again(
    ict_admin, registrar, programme, academic_year, institution, as_user
):
    clerk = as_user(registrar)
    clerk.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD444")]},
        format="json",
    )
    response = clerk.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD444")]},
        format="json",
    )
    conflict_id = response.data["results"][0]["conflict_id"]

    admin = as_user(ict_admin)
    url = f"/api/v1/sync/conflicts/{conflict_id}/resolve/"
    payload = {"resolution": ConflictResolution.DISMISSED, "reason": "Duplicate entry, discarded."}

    assert admin.post(url, payload, format="json").status_code == 200
    assert admin.post(url, payload, format="json").status_code == 409


@pytest.mark.integration
def test_a_registrar_cannot_resolve_conflicts_without_the_permission(
    registrar, programme, academic_year, institution, as_user
):
    """Viewing conflicts and deciding them are separate authorities."""
    client = as_user(registrar)
    client.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD333")]},
        format="json",
    )
    response = client.post(
        BATCH_URL,
        {"operations": [_op(programme, academic_year, national_id_number="SSD333")]},
        format="json",
    )
    conflict_id = response.data["results"][0]["conflict_id"]

    attempt = client.post(
        f"/api/v1/sync/conflicts/{conflict_id}/resolve/",
        {"resolution": ConflictResolution.DISMISSED, "reason": "Trying anyway"},
        format="json",
    )
    assert attempt.status_code == 403


# ------------------------------------------------------------- clock skew


@pytest.mark.integration
def test_a_wrong_device_clock_does_not_change_the_outcome(
    registrar, programme, academic_year, institution, as_user
):
    """Device clocks are frequently wrong. A timestamp from next year must not buy
    the operation any authority — the server's own receipt time is what counts.
    """
    client = as_user(registrar)
    operation = _op(programme, academic_year)
    operation["client_timestamp"] = (timezone.now() + timedelta(days=400)).isoformat()

    response = client.post(BATCH_URL, {"operations": [operation]}, format="json")
    assert response.data["results"][0]["status"] == SyncStatus.APPLIED

    record = SyncOperation.objects.get(client_op_id=operation["client_op_id"])
    assert record.client_timestamp > record.received_at  # stored as sent…
    assert record.received_at <= timezone.now()  # …but the server time is real


@pytest.mark.integration
def test_flag_for_review_never_overwrites(programme, academic_year, institution, registrar):
    """The rule that matters for marks and money: a divergent write is held, not
    applied. Verified directly against the engine with a FLAG_FOR_REVIEW handler.
    """

    @register_handler
    class MarkHandler:
        entity = "test.mark"
        actions = ("update",)
        conflict_policy = ConflictPolicy.FLAG_FOR_REVIEW
        required_permission = "registry.add_student"

        def apply(self, op, actor):
            raise SyncConflictDetected(
                field_name="score",
                server_value="68",
                client_value="82",
                server_updated_at=timezone.now(),
                message="Score already moderated; held for review.",
            )

    outcome = apply_operation(
        SyncOperationInput(
            client_op_id=str(uuid.uuid4()),
            entity="test.mark",
            action="update",
            payload={"score": 82},
        ),
        registrar,
    )

    assert outcome.status == SyncStatus.CONFLICT
    conflict = SyncConflict.objects.get(pk=outcome.conflict_id)
    assert conflict.server_value == "68"
    assert conflict.client_value == "82"
    assert conflict.status == ConflictResolution.OPEN


def test_apply_batch_preserves_submission_order(programme, academic_year, institution, registrar):
    inputs = [
        SyncOperationInput(
            client_op_id=str(uuid.uuid4()),
            entity="registry.student",
            action="create",
            payload=_student_payload(
                programme_id=programme.pk,
                entry_academic_year_id=academic_year.pk,
                first_name=f"Ordered{index}",
            ),
        )
        for index in range(3)
    ]

    results = apply_batch(inputs, registrar)
    assert [r["client_op_id"] for r in results] == [op.client_op_id for op in inputs]


def test_the_ledger_records_the_device(programme, academic_year, institution, registrar):
    """Useful when one laptop turns out to have a wrong clock or a bad operator."""
    apply_operation(
        SyncOperationInput(
            client_op_id=str(uuid.uuid4()),
            entity="registry.student",
            action="create",
            payload=_student_payload(
                programme_id=programme.pk, entry_academic_year_id=academic_year.pk
            ),
            device_id="registry-laptop-07",
        ),
        registrar,
    )
    assert SyncOperation.objects.filter(device_id="registry-laptop-07").exists()


def test_a_synced_record_links_back_to_its_operation(
    programme, academic_year, institution, registrar
):
    outcome = apply_operation(
        SyncOperationInput(
            client_op_id=str(uuid.uuid4()),
            entity="registry.student",
            action="create",
            payload=_student_payload(
                programme_id=programme.pk, entry_academic_year_id=academic_year.pk
            ),
        ),
        registrar,
    )

    record = SyncOperation.objects.get(client_op_id=outcome.client_op_id)
    assert record.target is not None
    assert record.target.pk == outcome.result["id"]
