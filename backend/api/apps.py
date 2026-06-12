from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "api"

    def ready(
        self,
    ) -> None:
        import api.checks  # noqa: F401
        import api.signals  # noqa: F401
