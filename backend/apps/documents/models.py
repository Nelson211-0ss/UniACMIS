"""Documents & certification (FR-DOC-01…04).

A transcript is requested, potentially many times over a graduate's life; a
certificate is issued once, following graduation clearance — different
enough workflows that they are not forced into one "document request"
model. Both end up as an `IssuedDocument`, the one thing a verifier ever
needs to check.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["DocumentType", "IssuedDocument", "TranscriptRequest", "TranscriptRequestStatus"]


class TranscriptRequestStatus(models.TextChoices):
    REQUESTED = "requested", _("Requested")
    REJECTED = "rejected", _("Rejected")
    ISSUED = "issued", _("Issued")


class TranscriptRequest(AuditedModel, TimeStampedModel):
    """FR-DOC-01. A student's own request for a copy of their transcript.
    Approving one and issuing the document are the same step — there is no
    daylight between "approved" and "the record exists", so no separate
    APPROVED status."""

    audit_fields = ("status",)

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="transcript_requests"
    )
    reason = models.TextField(_("reason"), blank=True)
    status = models.CharField(
        _("status"),
        max_length=15,
        choices=TranscriptRequestStatus.choices,
        default=TranscriptRequestStatus.REQUESTED,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decision_notes = models.TextField(_("decision notes"), blank=True)
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    class Meta:
        verbose_name = _("transcript request")
        verbose_name_plural = _("transcript requests")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student_id} [{self.status}]"


class DocumentType(models.TextChoices):
    TRANSCRIPT = "transcript", _("Transcript")
    CERTIFICATE = "certificate", _("Certificate")


class IssuedDocument(AuditedModel, TimeStampedModel):
    """FR-DOC-02. The one record `FR-DOC-03`'s public verification page
    reads — deliberately holding nothing beyond what confirming authenticity
    needs. A verifier is never shown grades or fees, only that this
    document, with this serial, was genuinely issued and has not been
    revoked."""

    audit_fields = ("is_revoked",)
    audit_sensitive = True

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="issued_documents"
    )
    document_type = models.CharField(_("type"), max_length=15, choices=DocumentType.choices)
    transcript_request = models.ForeignKey(
        TranscriptRequest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issued_documents",
    )
    serial_number = models.CharField(_("serial number"), max_length=40, unique=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    issued_at = models.DateTimeField(_("issued at"))
    is_revoked = models.BooleanField(_("revoked"), default=False)
    revoked_reason = models.TextField(_("revocation reason"), blank=True)
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)
    override_reason = models.TextField(
        _("clearance override reason"),
        blank=True,
        help_text=_("Set only when issued despite an open graduation-clearance hold."),
    )

    class Meta:
        verbose_name = _("issued document")
        verbose_name_plural = _("issued documents")
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["student", "document_type"])]
        permissions = [
            ("issue_certificate", _("Can issue a certificate")),
            ("revoke_document", _("Can revoke an issued document")),
            ("override_clearance", _("Can issue a certificate despite an open clearance hold")),
        ]

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked

    def __str__(self) -> str:
        return f"{self.serial_number} [{self.document_type}]"
