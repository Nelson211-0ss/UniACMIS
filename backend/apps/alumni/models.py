"""Alumni (FR-ALM-01…02)."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel

__all__ = ["AlumniEvent", "AlumniProfile", "EmploymentStatus"]


class EmploymentStatus(models.TextChoices):
    EMPLOYED = "employed", _("Employed")
    SELF_EMPLOYED = "self_employed", _("Self-employed")
    FURTHER_STUDY = "further_study", _("In further study")
    UNEMPLOYED = "unemployed", _("Unemployed")
    UNKNOWN = "unknown", _("Unknown")


class AlumniProfile(AuditedModel, TimeStampedModel):
    """FR-ALM-01. A graduate's contact and tracer data — kept separate from
    `registry.Student`'s own contact fields, which freeze at whatever they
    were on graduation day, so a tracer update never rewrites the academic
    record it is tracing."""

    audit_fields = ("employment_status", "is_contactable")

    student = models.OneToOneField(
        "registry.Student", on_delete=models.PROTECT, related_name="alumni_profile"
    )
    phone = models.CharField(_("phone"), max_length=32, blank=True)
    email = models.EmailField(_("email"), blank=True)
    current_employer = models.CharField(_("current employer"), max_length=200, blank=True)
    current_position = models.CharField(_("current position"), max_length=200, blank=True)
    employment_status = models.CharField(
        _("employment status"),
        max_length=15,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.UNKNOWN,
    )
    is_contactable = models.BooleanField(
        _("contactable"),
        default=True,
        help_text=_("Off once a tracer contact bounces or they opt out."),
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("alumni profile")
        verbose_name_plural = _("alumni profiles")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student_id} [{self.employment_status}]"


class AlumniEvent(AuditedModel, TimeStampedModel):
    """FR-ALM-02. A reunion, careers fair or homecoming — its own record
    distinct from an `Announcement`, which is the notice inviting alumni to
    it, not the event itself."""

    audit_fields = ("title", "event_date")

    title = models.CharField(_("title"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    event_date = models.DateField(_("date"))
    location = models.CharField(_("location"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("alumni event")
        verbose_name_plural = _("alumni events")
        ordering = ["-event_date"]

    def __str__(self) -> str:
        return f"{self.title} ({self.event_date})"
