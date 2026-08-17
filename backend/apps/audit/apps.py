from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Audit trail"

    def ready(self) -> None:
        # Register the audit implementation for `apps.core.ports.audit()`. core
        # is the lowest layer and must not import this app, so the dependency is
        # inverted: we hand ourselves to core at startup.
        from apps.audit.ports import DjangoAuditPort
        from apps.core.ports import AuditPort
        from apps.core.services.registry import registry

        registry.register(AuditPort, DjangoAuditPort())
