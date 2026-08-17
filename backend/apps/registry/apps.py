from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.registry"
    label = "registry"
    verbose_name = "Student and staff registry"

    def ready(self) -> None:
        # Registers the offline sync handler for student creation, so registry
        # clerks can keep working through a power or network outage.
        from apps.registry import sync  # noqa: F401
