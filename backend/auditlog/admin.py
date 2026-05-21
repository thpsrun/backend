from django.contrib import admin

from auditlog.models import GameAuditEvent


@admin.register(GameAuditEvent)
class GameAuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "game",
        "event_type",
        "actor_kind",
        "actor_label",
        "summary",
    )
    list_filter = ("event_type", "actor_kind", "game")
    search_fields = (
        "summary",
        "target_id",
        "actor_label",
        "game__slug",
        "game__name",
    )
    readonly_fields = tuple(f.name for f in GameAuditEvent._meta.get_fields())
    ordering = ("-created_at",)

    def has_add_permission(
        self,
        request,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request,
        obj=None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request,
        obj=None,
    ) -> bool:
        return request.user.is_superuser
