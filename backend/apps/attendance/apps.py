from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance"
    label = "attendance"
    verbose_name = "Attendance"

    def ready(self) -> None:
        # Registers the offline sync handler for session records, so a
        # lecturer can take a register through a power or network outage.
        from apps.attendance import sync  # noqa: F401
