from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        # Import kinds so the registry is populated at app startup.
        # Import signals so receivers are wired.
        from notifications import (  # noqa: F401
            kinds,
            signals,
        )
