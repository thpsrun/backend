from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import URLPattern, path, reverse

from nav.models import NavItem, SocialLink
from nav.views import ManageNavOrderingView


@admin.register(NavItem)
class NavItemAdmin(admin.ModelAdmin):
    list_display = ("indented_name", "url", "parent", "order", "is_visible")
    list_filter = ("is_visible", "parent")
    search_fields = ("name", "url")
    list_select_related = ("parent",)
    actions = ("manage_ordering",)

    @admin.display(description="Name")
    def indented_name(
        self,
        obj: NavItem,
    ) -> str:
        depth = 0
        current = obj.parent
        while current is not None:
            depth += 1
            current = current.parent
        prefix = "\u00a0\u00a0\u00a0\u00a0" * depth
        return f"{prefix}{obj.name}" if depth > 0 else obj.name

    @admin.action(description="Manage Nav Item Ordering")
    def manage_ordering(
        self,
        request: HttpRequest,
        queryset,
    ) -> HttpResponse:
        return redirect(reverse("admin:manage_nav_ordering"))

    def get_urls(
        self,
    ) -> list[URLPattern]:
        custom_urls = [
            path(
                "manage-ordering/",
                self.admin_site.admin_view(ManageNavOrderingView.as_view()),
                name="manage_nav_ordering",
            ),
        ]
        return custom_urls + super().get_urls()


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("platform", "url", "order", "is_visible")
    list_editable = ("order", "is_visible")
