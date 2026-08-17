"""
Celery application.

Used for anything that must not block a request on a slow or unreliable
dependency: SMS and email delivery, report generation, sync reconciliation.
Tasks are acknowledged late so that a worker killed mid-task by a power cut
leaves the task on the queue rather than silently dropping it.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("uniacmis")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:
    """Smoke test that the worker is reachable: `debug_task.delay()`."""
    return f"celery ok: {self.request.id}"
