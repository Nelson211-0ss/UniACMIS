from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
    label = "finance"
    verbose_name = "Finance"

    def ready(self) -> None:
        # Registers the real fee-balance hold provider (replacing the Phase 1
        # demo stub) and the offline sync handler for manual payment capture.
        from apps.finance import providers, sync  # noqa: F401

        providers.register()
