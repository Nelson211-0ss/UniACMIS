from django.apps import AppConfig


class LibraryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.library"
    label = "library"
    verbose_name = "Library"

    def ready(self) -> None:
        from apps.library import sync  # noqa: F401
