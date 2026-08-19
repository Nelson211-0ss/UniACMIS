"""Hostel: room inventory, allocation and the fee link to finance
(FR-HOS-01…03)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.choices import Gender
from apps.core.fields import CurrencyField, MoneyAmountField
from apps.core.models import SoftDeleteModel, TimeStampedModel

__all__ = ["Allocation", "AllocationStatus", "HostelPolicy", "Room"]


class Room(AuditedModel, TimeStampedModel, SoftDeleteModel):
    """FR-HOS-01. Single-sex by hall, the reality of every hostel this
    system targets — `gender_restriction` reuses the same `Gender` a
    student declares, so a room can only ever match a student exactly, never
    by a second, parallel vocabulary."""

    audit_fields = ("building", "room_number", "capacity", "gender_restriction", "is_active")

    building = models.CharField(_("building"), max_length=100)
    room_number = models.CharField(_("room number"), max_length=20)
    capacity = models.PositiveSmallIntegerField(_("capacity"), validators=[MinValueValidator(1)])
    gender_restriction = models.CharField(_("restricted to"), max_length=15, choices=Gender.choices)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("room")
        verbose_name_plural = _("rooms")
        ordering = ["building", "room_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["building", "room_number"], name="one_room_per_building_number"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.pk and self.gender_restriction:
            from apps.registry.services import gender_for_student

            active_student_ids = self.allocations.filter(
                status=AllocationStatus.ACTIVE
            ).values_list("student_id", flat=True)
            for student_id in active_student_ids:
                if gender_for_student(student_id) != self.gender_restriction:
                    raise ValidationError(
                        {
                            "gender_restriction": _(
                                "An active occupant does not match this restriction — vacate them first."
                            )
                        }
                    )

    @property
    def occupied_beds(self) -> int:
        return self.allocations.filter(status=AllocationStatus.ACTIVE).count()

    @property
    def available_beds(self) -> int:
        return max(0, self.capacity - self.occupied_beds)

    def __str__(self) -> str:
        return f"{self.building} {self.room_number}"


class AllocationStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    VACATED = "vacated", _("Vacated")


class Allocation(AuditedModel, TimeStampedModel):
    """FR-HOS-02. One row per stay — vacating never deletes the record, it
    closes it out, the same "history over overwrite" choice `hr.Contract`
    makes."""

    audit_fields = ("room", "status")

    student = models.ForeignKey(
        "registry.Student", on_delete=models.PROTECT, related_name="hostel_allocations"
    )
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="allocations")
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="hostel_allocations"
    )
    status = models.CharField(
        _("status"),
        max_length=15,
        choices=AllocationStatus.choices,
        default=AllocationStatus.ACTIVE,
    )
    allocated_at = models.DateTimeField(_("allocated at"))
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    vacated_at = models.DateTimeField(_("vacated at"), null=True, blank=True)
    vacated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("allocation")
        verbose_name_plural = _("allocations")
        ordering = ["-allocated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(status=AllocationStatus.ACTIVE),
                name="one_active_allocation_per_student",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.room_id and self.student_id:
            from apps.registry.services import gender_for_student

            student_gender = gender_for_student(self.student_id)
            if student_gender != self.room.gender_restriction:
                raise ValidationError(
                    {"room": _("This room is restricted to a gender the student did not declare.")}
                )

    def __str__(self) -> str:
        return f"{self.student_id} → {self.room_id} [{self.status}]"


class HostelPolicy(models.Model):
    """A singleton, the same shape as `library.LibraryPolicy` — the termly
    fee is data a hostel officer edits, never a constant (`FR-HOS-03`)."""

    termly_fee = MoneyAmountField(_("termly fee"), default=Decimal("0"))
    currency = CurrencyField()

    class Meta:
        verbose_name = _("hostel policy")
        verbose_name_plural = _("hostel policy")

    def __str__(self) -> str:
        return f"{self.termly_fee} {self.currency}/term"

    @classmethod
    def get(cls) -> HostelPolicy | None:
        return cls.objects.first()
