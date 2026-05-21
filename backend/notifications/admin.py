from django.contrib import admin

from notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "type",
        "title",
        "is_read",
        "target_type",
        "target_id",
    )
    list_filter = ("type", "is_read", "target_type")
    search_fields = (
        "title",
        "body",
        "user__username",
        "target_id",
    )
    readonly_fields = tuple(f.name for f in Notification._meta.get_fields())
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


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "enabled")
    list_filter = ("type", "enabled")
    search_fields = ("user__username", "type")
