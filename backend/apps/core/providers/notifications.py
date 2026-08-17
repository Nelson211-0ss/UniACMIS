"""
Notification providers.

Phase 1 ships a console implementation so that every notification path is
buildable and testable before a South Sudanese SMS aggregator is contracted
(SRS §8 open item 2). Phase 6 adds the real one behind the same interface.

Delivery is always attempted from a Celery task, never inline in a request: an
SMS gateway timing out must not block a registrar's save, and a failed send has
to be visible rather than lost.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.core.mail import send_mail

from apps.core.ports import DeliveryReceipt

logger = logging.getLogger(__name__)


class ConsoleNotificationProvider:
    """Logs instead of sending. Development and test default."""

    name = "console"

    def send_sms(self, to: str, body: str, ref: str = "") -> DeliveryReceipt:
        reference = ref or uuid.uuid4().hex
        logger.info("[SMS→%s] %s (ref=%s)", to, body, reference)
        return DeliveryReceipt(
            provider=self.name, channel="sms", reference=reference, accepted=True
        )

    def send_email(self, to: str, subject: str, body: str, ref: str = "") -> DeliveryReceipt:
        reference = ref or uuid.uuid4().hex
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost"),
            recipient_list=[to],
            fail_silently=True,
        )
        logger.info("[EMAIL→%s] %s (ref=%s)", to, subject, reference)
        return DeliveryReceipt(
            provider=self.name, channel="email", reference=reference, accepted=True
        )


class RecordingNotificationProvider(ConsoleNotificationProvider):
    """Keeps sent messages in memory so tests can assert on them."""

    name = "recording"

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_sms(self, to: str, body: str, ref: str = "") -> DeliveryReceipt:
        self.sent.append({"channel": "sms", "to": to, "body": body, "ref": ref})
        return DeliveryReceipt(
            provider=self.name, channel="sms", reference=ref or uuid.uuid4().hex, accepted=True
        )

    def send_email(self, to: str, subject: str, body: str, ref: str = "") -> DeliveryReceipt:
        self.sent.append(
            {"channel": "email", "to": to, "subject": subject, "body": body, "ref": ref}
        )
        return DeliveryReceipt(
            provider=self.name, channel="email", reference=ref or uuid.uuid4().hex, accepted=True
        )
