from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(
        self,
    ) -> None:
        """Import signal receivers so they register at app startup."""
        import accounts.signals  # noqa: F401
