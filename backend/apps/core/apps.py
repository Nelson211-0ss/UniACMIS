from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core"

    def ready(self) -> None:
        # Providers register themselves into the registry at startup so that
        # callers resolve them by interface rather than by import (ARCHITECTURE §4).
        from apps.core.providers import holds

        if getattr(settings, "ENABLE_DEMO_HOLD_PROVIDER", False):
            holds.register_demo_provider()
