from django.apps import AppConfig


class AuditLogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auditlog"
    verbose_name = "Audit Log"

    def ready(
        self,
    ) -> None:
        from auditlog import signals  # noqa: F401
