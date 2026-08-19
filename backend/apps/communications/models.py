"""Communications (FR-COM-01…03).

Campus-scoped audiences are out of scope — the single-campus deferral (D-1
in `docs/TRACEABILITY.md`) means there is only ever one campus to scope to.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["Announcement", "AudienceType"]


class AudienceType(models.TextChoices):
    ALL_STUDENTS = "all_students", _("All students")
    PROGRAMME = "programme", _('A specific programme ("class")')
    ALUMNI = "alumni", _("Alumni")


class Announcement(AuditedModel, TimeStampedModel):
    """FR-COM-01…02. Composing and sending are one act — there is no draft
    state, so nothing sits half-written where a reader might see it. The row
    itself is the portal notice; SMS and email are the same message fanned
    out to whichever contact channel each recipient has on file."""

    audit_fields = ("title", "audience_type", "recipient_count")
    audit_sensitive = True

    title = models.CharField(_("title"), max_length=200)
    body = models.TextField(_("body"))
    audience_type = models.CharField(_("audience"), max_length=15, choices=AudienceType.choices)
    programme = models.ForeignKey(
        "curriculum.Programme",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="announcements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sent_at = models.DateTimeField(_("sent at"))
    recipient_count = models.PositiveIntegerField(_("recipients"), default=0)
    sms_sent_count = models.PositiveIntegerField(_("SMS sent"), default=0)
    email_sent_count = models.PositiveIntegerField(_("emails sent"), default=0)

    class Meta:
        verbose_name = _("announcement")
        verbose_name_plural = _("announcements")
        ordering = ["-sent_at"]
        permissions = [
            ("send_announcement", _('Can send an announcement to a programme ("class")')),
            ("broadcast_all", _("Can send an announcement to every student institution-wide")),
        ]

    def clean(self) -> None:
        super().clean()
        if self.audience_type == AudienceType.PROGRAMME and self.programme_id is None:
            raise ValidationError({"programme": _("Required for a programme-scoped announcement.")})
        if self.audience_type != AudienceType.PROGRAMME and self.programme_id is not None:
            raise ValidationError({"programme": _("Only set for a programme-scoped announcement.")})

    def __str__(self) -> str:
        return f"{self.title} [{self.audience_type}]"
