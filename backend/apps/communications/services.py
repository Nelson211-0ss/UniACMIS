"""Communications services (FR-COM-01…03)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.communications.models import Announcement, AudienceType
from apps.core.exceptions import DomainError
from apps.core.providers import get_notification_provider

logger = logging.getLogger(__name__)


class BroadcastNotPermitted(DomainError):
    code = "broadcast_not_permitted"


class OutsideOwnDepartment(DomainError):
    code = "outside_own_department"


class ProgrammeRequired(DomainError):
    code = "programme_required"


@transaction.atomic
def send_announcement(
    *, title: str, body: str, audience_type: str, programme_id: int | None = None, actor: Any
) -> Announcement:
    """Sending is best-effort per recipient, the same shape
    `admissions._notify_decision` uses: one unreachable phone number or
    invalid address must not stop the rest of the audience from being
    reached, and must not roll back the announcement record itself."""
    from apps.alumni.services import active_alumni_contacts
    from apps.curriculum.services import department_id_for_programme
    from apps.registry.services import active_student_contacts

    if audience_type == AudienceType.ALL_STUDENTS:
        if not (actor and actor.has_perm("communications.broadcast_all")):
            raise BroadcastNotPermitted("You may not broadcast to every student.")
        contacts = active_student_contacts()
    elif audience_type == AudienceType.ALUMNI:
        if not (actor and actor.has_perm("communications.broadcast_all")):
            raise BroadcastNotPermitted("You may not message alumni institution-wide.")
        contacts = active_alumni_contacts()
    elif audience_type == AudienceType.PROGRAMME:
        if programme_id is None:
            raise ProgrammeRequired("A programme is required for a class announcement.")
        if (
            actor is not None
            and actor.has_role("hod")
            and not actor.has_role("registrar", "management", "ict_admin")
        ):
            own_department_id = getattr(
                getattr(actor, "staff_profile", None), "department_id", None
            )
            if own_department_id != department_id_for_programme(programme_id):
                raise OutsideOwnDepartment(
                    "You may only announce to your own department's programmes."
                )
        contacts = active_student_contacts(programme_id=programme_id)
    else:  # pragma: no cover — model.clean() rejects any other value first
        contacts = []

    provider = get_notification_provider()
    sms_sent = email_sent = 0
    for contact in contacts:
        try:
            if contact.get("phone"):
                provider.send_sms(contact["phone"], body)
                sms_sent += 1
            if contact.get("email"):
                provider.send_email(contact["email"], subject=title, body=body)
                email_sent += 1
        except Exception:
            logger.exception("Failed to notify student %s of an announcement", contact.get("id"))

    announcement = Announcement(
        title=title,
        body=body,
        audience_type=audience_type,
        programme_id=programme_id,
        created_by=actor if getattr(actor, "pk", None) else None,
        sent_at=timezone.now(),
        recipient_count=len(contacts),
        sms_sent_count=sms_sent,
        email_sent_count=email_sent,
    )
    announcement.audit_reason = f"Sent to {len(contacts)} recipient(s)"
    announcement.full_clean()
    announcement.save()
    return announcement
