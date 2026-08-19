"""Alumni services (FR-ALM-01…02)."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.alumni.models import AlumniEvent, AlumniProfile
from apps.core.exceptions import DomainError


class NotYetGraduated(DomainError):
    code = "not_yet_graduated"


@transaction.atomic
def create_alumni_profile(*, student_id: int, actor: Any = None, **fields: Any) -> AlumniProfile:
    from apps.registry.services import is_graduated

    if not is_graduated(student_id):
        raise NotYetGraduated("Only a graduated student may have an alumni profile.")

    profile = AlumniProfile(student_id=student_id, **fields)
    profile.audit_reason = "Alumni profile created"
    profile.full_clean()
    profile.save()
    return profile


@transaction.atomic
def update_alumni_profile(
    profile: AlumniProfile, *, actor: Any = None, **fields: Any
) -> AlumniProfile:
    for name, value in fields.items():
        setattr(profile, name, value)
    profile.audit_reason = "Alumni profile updated"
    profile.full_clean()
    profile.save()
    return profile


@transaction.atomic
def create_alumni_event(*, actor: Any = None, **fields: Any) -> AlumniEvent:
    event = AlumniEvent(**fields)
    event.audit_reason = "Alumni event scheduled"
    event.full_clean()
    event.save()
    return event


@transaction.atomic
def update_alumni_event(event: AlumniEvent, *, actor: Any = None, **fields: Any) -> AlumniEvent:
    for name, value in fields.items():
        setattr(event, name, value)
    event.audit_reason = "Alumni event updated"
    event.full_clean()
    event.save()
    return event


def active_alumni_contacts() -> list[dict[str, Any]]:
    """The audience `communications.send_announcement`'s `alumni` audience
    type fans out to — a service call rather than an `AlumniProfile`
    import."""
    return list(AlumniProfile.objects.filter(is_contactable=True).values("id", "phone", "email"))
