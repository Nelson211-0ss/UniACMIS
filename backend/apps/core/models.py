"""Core abstract models and the infrastructure tables (ID sequences, sync ledger)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):  # type: ignore[override]
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    def get_queryset(self) -> SoftDeleteQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    """Rows that must never actually disappear.

    Academic history has to stay reconstructable for decades — a transcript
    issued in 2040 refers to a programme and courses as they were. Hard-deleting
    a programme would orphan every result that referenced it, and reusing a
    deleted student's ID would breach FR-REG-01.

    `objects` hides deleted rows; `all_objects` sees everything.
    """

    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, using=None, keep_parents=False, hard: bool = False):  # type: ignore[override]
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = timezone.now()
        self.save(
            update_fields=(
                ["deleted_at", "updated_at"] if hasattr(self, "updated_at") else ["deleted_at"]
            )
        )
        return (1, {self._meta.label: 1})

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class IdSequence(models.Model):
    """Race-free counters for human-facing identifiers.

    Student IDs (FR-REG-01), and later receipt, invoice and certificate serials,
    are printed on documents people rely on. `max(id) + 1` cannot promise
    uniqueness when two registry clerks admit students at the same moment, so
    allocation takes a row lock.
    """

    scope = models.CharField(_("scope"), max_length=120, unique=True)
    last_value = models.PositiveIntegerField(_("last value"), default=0)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("ID sequence")
        verbose_name_plural = _("ID sequences")
        ordering = ["scope"]

    def __str__(self) -> str:
        return f"{self.scope} → {self.last_value}"

    @classmethod
    def allocate(cls, scope: str) -> int:
        """Return the next value for `scope`, locking the row until commit.

        Must be called inside a transaction if the caller needs the allocation to
        be atomic with whatever it is numbering: on rollback the counter still
        advances, which leaves a gap. A gap is harmless; a duplicate is not.
        """
        # Savepoint, so a lost create race doesn't poison the caller's transaction.
        try:
            with transaction.atomic():
                cls.objects.create(scope=scope)
        except IntegrityError:
            pass

        with transaction.atomic():
            row = cls.objects.select_for_update().get(scope=scope)
            row.last_value += 1
            row.save(update_fields=["last_value", "updated_at"])
            return row.last_value

    @classmethod
    def peek(cls, scope: str) -> int:
        row = cls.objects.filter(scope=scope).first()
        return row.last_value if row else 0


# --------------------------------------------------------------- sync ledger


class SyncStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    APPLIED = "applied", _("Applied")
    DUPLICATE = "duplicate", _("Duplicate (already applied)")
    CONFLICT = "conflict", _("Conflict — held for review")
    REJECTED = "rejected", _("Rejected")


class SyncAction(models.TextChoices):
    CREATE = "create", _("Create")
    UPDATE = "update", _("Update")
    DELETE = "delete", _("Delete")


class ConflictPolicy(models.TextChoices):
    LAST_WRITE_WINS = "last_write_wins", _("Last write wins (overwrite is audited)")
    FLAG_FOR_REVIEW = "flag_for_review", _("Flag for human review")


class SyncOperation(models.Model):
    """Idempotency ledger for offline writes (NFR-AVAIL-01).

    A dropped connection mid-flush is the normal case here, not an edge case, so
    the client retries whole batches. `client_op_id` is generated on the device
    and unique here, which makes a replay a no-op that returns the original
    result instead of creating a second record.
    """

    client_op_id = models.UUIDField(_("client operation id"), unique=True)
    entity = models.CharField(_("entity"), max_length=100)
    action = models.CharField(_("action"), max_length=10, choices=SyncAction.choices)
    payload = models.JSONField(_("payload"), default=dict)

    # Device clocks are frequently wrong. Recorded for ordering within one
    # device's own stream and for dispute resolution — never used as the
    # authoritative time for audit or reporting.
    client_timestamp = models.DateTimeField(_("client timestamp"), null=True, blank=True)
    received_at = models.DateTimeField(_("received at"), auto_now_add=True, db_index=True)

    status = models.CharField(
        _("status"), max_length=12, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    result = models.JSONField(_("result"), null=True, blank=True)
    error_detail = models.TextField(_("error detail"), blank=True)

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_operations",
    )
    device_id = models.CharField(_("device id"), max_length=100, blank=True)

    target_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    class Meta:
        verbose_name = _("sync operation")
        verbose_name_plural = _("sync operations")
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["entity", "status"]),
            models.Index(fields=["submitted_by", "-received_at"]),
            models.Index(fields=["device_id", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.entity}.{self.action} [{self.status}]"


class ConflictResolution(models.TextChoices):
    OPEN = "open", _("Open")
    RESOLVED_SERVER = "resolved_server", _("Resolved — kept server value")
    RESOLVED_CLIENT = "resolved_client", _("Resolved — accepted client value")
    DISMISSED = "dismissed", _("Dismissed")


class SyncConflict(models.Model):
    """A divergent offline write that was **not** applied.

    Raised by entities whose conflict policy is FLAG_FOR_REVIEW — marks and
    money. Silently overwriting a grade because a laptop's clock ran fast is a
    fraud vector, not a merge strategy, so a human decides.
    """

    sync_operation = models.ForeignKey(
        SyncOperation, on_delete=models.CASCADE, related_name="conflicts"
    )
    entity = models.CharField(_("entity"), max_length=100)

    target_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    field_name = models.CharField(_("field"), max_length=100, blank=True)
    server_value = models.TextField(_("server value"), blank=True)
    client_value = models.TextField(_("client value"), blank=True)
    server_updated_at = models.DateTimeField(null=True, blank=True)
    client_timestamp = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ConflictResolution.choices,
        default=ConflictResolution.OPEN,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_sync_conflicts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_reason = models.TextField(_("resolution reason"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("sync conflict")
        verbose_name_plural = _("sync conflicts")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]
        permissions = [
            ("resolve_syncconflict", _("Can resolve sync conflicts")),
        ]

    def __str__(self) -> str:
        return f"{self.entity}.{self.field_name} [{self.status}]"

    @property
    def is_open(self) -> bool:
        return self.status == ConflictResolution.OPEN


def new_client_op_id() -> uuid.UUID:
    """Server-side helper for tests and staff-entry paths that need an id."""
    return uuid.uuid4()
