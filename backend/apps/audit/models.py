"""
The audit trail (FR-RPT-04, NFR-SEC-03).

Two properties distinguish this from ordinary logging, and both exist because the
system is expected to reduce fraud in grading and fee collection:

**Append-only.** No code path updates or deletes an entry. In production the
application's database role is not granted UPDATE or DELETE on this table either,
so a compromised application account still cannot rewrite history.

**Tamper-evident.** Each row carries `sha256(prev_hash + canonical_payload)`.
Editing or removing a historical row breaks the chain at a detectable point;
`verify_audit_chain` finds it. A log that can be quietly edited by anyone with
database access is not evidence of anything.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

GENESIS_HASH = "0" * 64


class AuditAction(models.TextChoices):
    CREATE = "create", _("Created")
    UPDATE = "update", _("Updated")
    DELETE = "delete", _("Deleted")
    LOGIN = "login", _("Signed in")
    LOGOUT = "logout", _("Signed out")
    LOGIN_FAILED = "login_failed", _("Failed sign-in")
    VIEW_SENSITIVE = "view_sensitive", _("Viewed sensitive record")
    APPROVE = "approve", _("Approved")
    REJECT = "reject", _("Rejected")
    ROLE_GRANT = "role_grant", _("Role granted")
    ROLE_REVOKE = "role_revoke", _("Role revoked")
    SYNC_OVERWRITE = "sync_overwrite", _("Overwritten by offline sync")
    EXPORT = "export", _("Exported data")


class AuditLogQuerySet(models.QuerySet):
    def delete(self):  # type: ignore[override]
        raise IntegrityError(
            "Audit entries are append-only and cannot be deleted. "
            "Retention is handled by a reviewed archival process, not ad-hoc deletion."
        )

    def update(self, **kwargs):  # type: ignore[override]
        raise IntegrityError("Audit entries are append-only and cannot be modified.")

    def for_object(self, instance) -> AuditLogQuerySet:
        return self.filter(
            content_type=ContentType.objects.get_for_model(instance),
            object_id=str(instance.pk),
        )


class AuditLog(models.Model):
    """One row per changed field, or per non-field action."""

    # ---- what changed ----
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(_("object id"), max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")
    object_repr = models.CharField(
        _("object"),
        max_length=255,
        blank=True,
        help_text=_("Label captured at write time, so the entry stays readable."),
    )

    action = models.CharField(_("action"), max_length=20, choices=AuditAction.choices)
    field_name = models.CharField(_("field"), max_length=100, blank=True)
    # NULL is meaningful here, so DJ001's usual advice does not apply: it
    # separates "the field was empty" from "this row is not about a field change
    # at all" (a login, an approval). Collapsing both to "" would lose that.
    old_value = models.TextField(_("old value"), null=True, blank=True)  # noqa: DJ001
    new_value = models.TextField(_("new value"), null=True, blank=True)  # noqa: DJ001
    description = models.CharField(_("description"), max_length=255, blank=True)

    # A diff says what changed; only a person can say why. Mandatory for grade
    # and financial changes, which is where disputes actually arise.
    reason = models.TextField(_("reason"), blank=True)

    # ---- who ----
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    # Snapshotted, so the entry survives the actor being renamed or deleted.
    actor_name = models.CharField(_("actor"), max_length=150, blank=True)
    actor_role = models.CharField(_("actor role"), max_length=100, blank=True)

    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    request_id = models.CharField(_("request id"), max_length=64, blank=True, db_index=True)

    # `default`, not `auto_now_add`: the row hash covers the stored timestamp, and
    # auto_now_add would overwrite the value at insert time with a slightly later
    # one, leaving every entry failing its own verification.
    created_at = models.DateTimeField(
        _("recorded at"), default=timezone.now, editable=False, db_index=True
    )

    # ---- tamper evidence ----
    prev_hash = models.CharField(max_length=64, default=GENESIS_HASH, editable=False)
    row_hash = models.CharField(max_length=64, unique=True, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("audit entry")
        verbose_name_plural = _("audit trail")
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["content_type", "object_id", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        who = self.actor_name or "system"
        what = f"{self.object_repr}.{self.field_name}" if self.field_name else self.object_repr
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {who} {self.action} {what}".strip()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise IntegrityError(
                "Audit entries are append-only; an existing entry cannot be re-saved."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise IntegrityError("Audit entries cannot be deleted.")

    @property
    def changed(self) -> str:
        if not self.field_name:
            return self.description
        return f"{self.field_name}: {self.old_value!r} → {self.new_value!r}"


class AuditedModel(models.Model):
    """Mixin that records field-level changes for the fields it declares.

    Declaring the fields explicitly rather than tracking everything is
    deliberate: a trail that logs every `updated_at` bump buries the two changes
    a registrar actually needs to find.

        class Student(AuditedModel):
            audit_fields = ("status", "programme", "current_level")
            audit_sensitive = False

    Set `audit_sensitive = True` on models holding grades or money: their audit
    entry is written in the same transaction as the change, so a failure to
    record rolls the change back. Losing the record of a mark change is worse
    than failing the change.

    Callers can supply the "why" before saving:

        student.audit_reason = "Suspended pending disciplinary hearing"
        student.save()
    """

    audit_fields: tuple[str, ...] = ()
    audit_sensitive: bool = False

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Test on `pk`, not on `_state.adding`: Django's `from_db()` constructs
        # the instance first and only flips `adding` to False afterwards, so at
        # this point every loaded row would look brand new and no change would
        # ever be detected.
        self._audit_snapshot = self._audit_values() if self.pk is not None else None
        self.audit_reason: str = ""

    def save(self, *args, **kwargs):
        from django.db import transaction

        from apps.audit.services import record_action, record_change

        is_create = self._state.adding
        previous = self._audit_snapshot
        reason = getattr(self, "audit_reason", "") or ""

        def _write() -> None:
            super(AuditedModel, self).save(*args, **kwargs)
            current = self._audit_values()

            if is_create:
                record_action(
                    instance=self,
                    action=AuditAction.CREATE,
                    description=f"Created {self._meta.verbose_name}",
                    reason=reason,
                )
            elif previous is not None:
                for name, new_value in current.items():
                    old_value = previous.get(name)
                    if old_value != new_value:
                        record_change(
                            instance=self,
                            field_name=name,
                            old_value=old_value,
                            new_value=new_value,
                            reason=reason,
                        )

            self._audit_snapshot = current

        if self.audit_sensitive:
            with transaction.atomic():
                _write()
        else:
            _write()

        return self

    def delete(self, *args, **kwargs):
        from apps.audit.services import record_action

        record_action(
            instance=self,
            action=AuditAction.DELETE,
            description=f"Deleted {self._meta.verbose_name}",
            reason=getattr(self, "audit_reason", "") or "",
        )
        return super().delete(*args, **kwargs)

    def _audit_values(self) -> dict[str, object]:
        """Current values of the audited fields.

        Reads FK columns by `attname` (`programme_id`) rather than following the
        relation, and skips deferred columns. Snapshotting happens on every
        instance load, so it must never issue a query of its own — that would
        turn one list view into N.
        """
        values: dict[str, object] = {}
        deferred = self.get_deferred_fields()
        for name in self.audit_fields:
            try:
                field = self._meta.get_field(name)
            except Exception:
                continue
            attname = getattr(field, "attname", name)
            if attname in deferred:
                continue
            values[name] = getattr(self, attname, None)
        return values
