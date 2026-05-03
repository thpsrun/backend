from __future__ import annotations

import re

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.html import escape, format_html
from django.utils.safestring import SafeString, mark_safe


class APIActivityLogEntryAdmin(admin.ModelAdmin):
    """Enhanced admin view for LogEntry to better display API activities."""

    list_display = [
        "action_time",
        "user_display",
        "content_type",
        "object_link",
        "action_flag_display",
        "change_message_display",
    ]

    list_filter = [
        "action_flag",
        "action_time",
        "content_type",
        "user__username",
    ]

    search_fields = [
        "object_repr",
        "change_message",
        "user__username",
        "user__first_name",
        "user__last_name",
    ]

    readonly_fields = [
        "action_time",
        "user",
        "content_type",
        "object_id",
        "object_repr",
        "action_flag",
        "change_message",
    ]

    date_hierarchy = "action_time"

    ordering = ["-action_time"]

    def has_add_permission(
        self,
        request: HttpRequest,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: LogEntry | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: LogEntry | None = None,
    ) -> bool:
        return getattr(request.user, "is_superuser", False)

    @admin.display(
        description="User/API Key",
        ordering="user__username",
    )
    def user_display(
        self,
        obj: LogEntry,
    ) -> SafeString | str:
        if obj.user:
            if obj.user.username.startswith("api_key_"):
                key_name: str = obj.user.last_name or obj.user.username.replace(
                    "api_key_", ""
                )
                return format_html(
                    '<span title="API Key: {}">' "<strong> {}</strong>" "</span>",
                    obj.user.username,
                    key_name,
                )
            else:
                return format_html(
                    '<span title="User: {}">' "<strong> {}</strong>" "</span>",
                    obj.user.username,
                    obj.user.get_full_name() or obj.user.username,
                )
        return "-"

    @admin.display(
        description="Action",
        ordering="action_flag",
    )
    def action_flag_display(
        self,
        obj: LogEntry,
    ) -> SafeString:
        """Display action with colored icons."""
        flag_display: dict[int, tuple[str, str, str]] = {
            1: ("➕", "Added", "#28a745"),
            2: ("✏️", "Changed", "#ffc107"),
            3: ("❌", "Deleted", "#dc3545"),
        }

        icon, text, color = flag_display.get(
            obj.action_flag, ("❓", "Unknown", "#6c757d")
        )

        return format_html(
            '<span style="color: {};" title="{}">{} {}</span>', color, text, icon, text
        )

    @admin.display(
        description="Object",
        ordering="object_repr",
    )
    def object_link(
        self,
        obj: LogEntry,
    ) -> SafeString | str:
        """Create a link to the actual object if possible."""
        if obj.content_type and obj.object_id:
            try:
                model_class = obj.content_type.model_class()
                if model_class:
                    try:
                        admin_url: str = reverse(
                            f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                            args=[obj.object_id],
                        )

                        return format_html(
                            '<a href="{}" target="_blank">{}</a>',
                            admin_url,
                            obj.object_repr,
                        )
                    except NoReverseMatch:
                        return format_html(
                            '<span style="color: #6c757d; '
                            'text-decoration: line-through;">{}</span>',
                            obj.object_repr,
                        )
            except Exception:
                pass

        return obj.object_repr or "-"

    @admin.display(
        description="Details",
        ordering="change_message",
    )
    def change_message_display(
        self,
        obj: LogEntry,
    ) -> SafeString | str:
        """Display change message with better formatting."""
        if not obj.change_message:
            return "-"

        message: str = escape(obj.change_message)

        if "via API" in message:
            message = message.replace("via API", "<strong>via API</strong>")

        if "Key:" in message:
            message = re.sub(
                r"Key: ([^)]+)",
                r'Key: <code style="background: #f8f9fa; padding: 2px 4px;'
                r'border-radius: 3px;">\1</code>',
                message,
            )

        return mark_safe(message)


admin.site.register(LogEntry, APIActivityLogEntryAdmin)
