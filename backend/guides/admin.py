from django.contrib import admin

from guides.models import Guides, Tags


@admin.register(Tags)
class TagsAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "description")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(Guides)
class GuidesAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "game", "created_at", "updated_at")
    list_filter = ("game", "tags", "created_at")
    search_fields = ("title", "short_description", "content", "owner__username")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("tags",)
    raw_id_fields = ("owner",)
    ordering = ("-created_at",)

    fieldsets = (
        ("Basic Information", {"fields": ("title", "slug", "owner", "game", "tags")}),
        ("Content", {"fields": ("short_description", "content")}),
    )
