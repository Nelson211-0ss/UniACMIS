from django.apps import AppConfig


class ExaminationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.examinations"
    label = "examinations"
    verbose_name = "Examinations and results"

    def ready(self) -> None:
        # Registers the offline sync handler for CA score entry.
        from apps.examinations import sync  # noqa: F401
