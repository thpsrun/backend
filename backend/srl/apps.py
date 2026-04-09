from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "srl"

    def ready(self) -> None:
        import srl.signals  # noqa: F401
