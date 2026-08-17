"""
Student and staff identifier generation (FR-REG-01).

The format comes from institutional configuration, not from code, and the
sequence number is allocated under a row lock. Two registry clerks admitting
students at the same moment must not be able to mint the same ID — this number is
printed on a certificate, so a duplicate is not something that can be quietly
fixed later.

IDs are never reused. Sequence counters only ever increase, and student records
are soft-deleted, so a withdrawn student's number stays retired.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.services import config
from apps.core.models import IdSequence
from apps.curriculum.services import id_tokens_for_programme

logger = logging.getLogger(__name__)


class IdTemplateError(ValidationError):
    """The configured template cannot be rendered."""


def _render(template: str, tokens: dict[str, object]) -> str:
    try:
        return template.format(**tokens)
    except KeyError as exc:
        raise IdTemplateError(
            f"The ID template refers to {exc} which is not a known placeholder. "
            f"Available: {', '.join(sorted(str(k) for k in tokens))}."
        ) from exc
    except (ValueError, IndexError) as exc:
        raise IdTemplateError(f"The ID template '{template}' is malformed: {exc}") from exc


def sequence_scope(faculty_code: str, programme_code: str, entry_year: str | int) -> str:
    """Counters are per faculty + programme + intake year.

    Scoping this way keeps the visible numbers small and meaningful ("the 42nd
    civil engineer admitted in 2026") instead of one global counter in the tens of
    thousands.
    """
    return f"student_id:{faculty_code}:{programme_code}:{entry_year}"


@transaction.atomic
def generate_student_id(programme_id: int, entry_year_name: str) -> str:
    """Allocate the next student ID for a programme and intake year.

    `entry_year_name` is an academic year name such as "2026/2027"; the leading
    calendar year is used, since that is what appears on documents.
    """
    tokens = id_tokens_for_programme(programme_id)
    year = str(entry_year_name).split("/")[0].strip()

    scope = sequence_scope(tokens["faculty"], tokens["programme"], year)
    sequence = IdSequence.allocate(scope)

    template = config.student_id_template()
    return _render(
        template,
        {
            "faculty": tokens["faculty"],
            "programme": tokens["programme"],
            "department": tokens["department"],
            "year": year,
            "seq": sequence,
        },
    )


@transaction.atomic
def generate_staff_number(year: str | int) -> str:
    year = str(year).split("/")[0].strip()
    sequence = IdSequence.allocate(f"staff_number:{year}")
    return _render(config.staff_id_template(), {"year": year, "seq": sequence})
