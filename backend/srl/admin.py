from typing import Any

from django import forms
from django.contrib import admin
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import URLPattern, path, reverse

from srl.models import (
    Awards,
    Categories,
    CountryCodes,
    Games,
    Levels,
    NowStreaming,
    Platforms,
    Players,
    RunPlayers,
    Runs,
    RunVariableValues,
    SRCSyncTask,
    Variables,
    VariableValues,
)
from srl.views import (
    GameReorderView,
    GameVisibilityView,
    LegacyOrderingRedirectView,
    LegacyVisibilityRedirectView,
    ManageGameDisplayView,
    RefreshGameRunsView,
    UpdateGameRunsView,
    UpdateGameView,
    UpdatePlayerView,
)


class GameAdmin(admin.ModelAdmin):
    """Admin panel used with the `Games` model.

    This panel is for the administration for the `Games` model.

    Methods:
        - update_game: Updates the metadata for all selected games from the Speedrun.com API.
        - update_game_runs: Updates the metadata for all runs within the selected games from the
            Speedrun.com API. This includes information that updates virtually all models.
                - Note: This is moderately intensive. Expect this to take time, especially with
                    rate limiting.
        - refresh_game_runs: Removes all runs from within the selected games and re-retrieves them
            from the Speedrun.com API.
                - Note: This is moderately intensive. Expect this to take time, especially with
                    rate limiting.
                - Note 2: All runs that were deleted this way and are also deleted on SRC are
                    forever lost.
    """

    list_display = ["name"]
    actions = [
        "update_game",
        "update_game_runs",
        "refresh_game_runs",
        "manage_main_visibility",
        "manage_ordering",
    ]
    search_fields = ["name"]

    @admin.action(description="Update Game Metadata")
    def update_game(
        self,
        _: HttpRequest,
        queryset: QuerySet["Games"],
    ) -> HttpResponse:
        """Updates the metadata for all selected games from the SRC API."""
        game_ids = [obj.id for obj in queryset]
        return redirect(
            reverse("admin:update_game") + f"?game_ids={','.join(game_ids)}"
        )

    @admin.action(description="Update Game Runs")
    def update_game_runs(
        self,
        _: HttpRequest,
        queryset: QuerySet["Games"],
    ) -> HttpResponse:
        """Updates the metadata for all runs of all selected games from the SRC API."""
        game_ids = [obj.id for obj in queryset]
        return redirect(
            reverse("admin:update_game_runs") + f"?game_ids={','.join(game_ids)}"
        )

    @admin.action(description="(Destructive) Rebuild Game Runs")
    def refresh_game_runs(
        self,
        _: HttpRequest,
        queryset: QuerySet["Games"],
    ) -> HttpResponse:
        """Removes all runs and re-retrieves them from the SRC API to re-import them."""
        game_ids = [obj.id for obj in queryset]
        return redirect(
            reverse("admin:refresh_game_runs") + f"?game_ids={','.join(game_ids)}"
        )

    @admin.action(description="Manage Main Page Visibility")
    def manage_main_visibility(
        self,
        _: HttpRequest,
        queryset: QuerySet["Games"],
    ) -> HttpResponse:
        """Opens the merged display editor for the selected game."""
        game = queryset.first()
        if game:
            return redirect(
                reverse("admin:srl_game_display", args=[game.id]),
            )
        return redirect(reverse("admin:srl_games_changelist"))

    @admin.action(description="Manage Category & Level Ordering")
    def manage_ordering(
        self,
        _: HttpRequest,
        queryset: QuerySet["Games"],
    ) -> HttpResponse:
        """Opens the merged display editor for the selected game."""
        game = queryset.first()
        if game:
            return redirect(
                reverse("admin:srl_game_display", args=[game.id]),
            )
        return redirect(reverse("admin:srl_games_changelist"))

    def get_urls(
        self,
    ) -> list[URLPattern]:
        """Adds all above methods to custom URLs."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "update-game/",
                self.admin_site.admin_view(UpdateGameView.as_view()),
                name="update_game",
            ),
            path(
                "update-game-runs/",
                self.admin_site.admin_view(UpdateGameRunsView.as_view()),
                name="update_game_runs",
            ),
            path(
                "refresh-game-runs/",
                self.admin_site.admin_view(RefreshGameRunsView.as_view()),
                name="refresh_game_runs",
            ),
            path(
                "<str:game_id>/manage-display/",
                self.admin_site.admin_view(ManageGameDisplayView.as_view()),
                name="srl_game_display",
            ),
            path(
                "<str:game_id>/reorder/",
                self.admin_site.admin_view(GameReorderView.as_view()),
                name="srl_game_reorder",
            ),
            path(
                "<str:game_id>/visibility/",
                self.admin_site.admin_view(GameVisibilityView.as_view()),
                name="srl_game_visibility",
            ),
            path(
                "<str:game_id>/manage-main-visibility/",
                self.admin_site.admin_view(LegacyVisibilityRedirectView.as_view()),
                name="srl_game_legacy_main_visibility",
            ),
            path(
                "<str:game_id>/manage-ordering/",
                self.admin_site.admin_view(LegacyOrderingRedirectView.as_view()),
                name="srl_game_legacy_ordering",
            ),
        ]
        return custom_urls + urls


class DefaultAdmin(admin.ModelAdmin):
    """Admin panel should be used if the Model has no real optons to sort."""

    list_display = ["name"]
    search_fields = ["name"]


class CategoriesAdmin(admin.ModelAdmin):
    """Admin panel used with the `Categories` model."""

    list_display = ["name"]
    search_fields = ["id"]
    list_filter = ["game"]


class VariableValuesAdmin(admin.ModelAdmin):
    """Admin panel used with the `VariableValues` model."""

    list_display = [
        "name",
        "var",
        "var__game",
        "appear_on_main",
    ]
    search_fields = ["name"]
    list_filter = ["var__game", "var__scope", "appear_on_main"]


class RunVariableValuesInline(admin.TabularInline):
    """Admin panel used with the `RunVariableValues` model."""

    model = RunVariableValues
    extra = 1
    autocomplete_fields = ["variable", "value"]


class RunPlayersInline(admin.TabularInline):
    """Admin panel used with the `RunPlayers` model."""

    model = RunPlayers
    extra = 1
    autocomplete_fields = ["player"]
    fields = ["player", "order"]
    verbose_name = "Player"
    verbose_name_plural = "Players"


class SpeedrunAdmin(admin.ModelAdmin):
    """Admin panel used with the `Runs` model.

    This panel is for the administration for the `Runs` model.

    Methods:
        - formfield_for_foreignkey: Inlines the `RunVariableValues` information and embeds it into
            each specific run.
    """

    list_display = ["id"]
    search_fields = ["id"]
    list_filter = ["runtype", "obsolete", "game", "platform"]
    inlines = [RunPlayersInline, RunVariableValuesInline]

    def formfield_for_foreignkey(
        self,
        db_field: models.ForeignKey[Any, Any],  # type: ignore
        request: HttpRequest | None,
        **kwargs: Any,
    ) -> forms.ModelChoiceField:
        """Inlines the `RunVariableValues` model into a `Runs` object."""
        if db_field.name in ["category", "level"]:
            if request:
                if (
                    request.resolver_match
                    and "object_id" in request.resolver_match.kwargs
                ):
                    run_id = request.resolver_match.kwargs["object_id"]
                    try:
                        run = Runs.objects.select_related("game").get(id=run_id)
                        if db_field.name == "category":
                            kwargs["queryset"] = Categories.objects.filter(
                                game=run.game
                            )
                        elif db_field.name == "level":
                            kwargs["queryset"] = Levels.objects.filter(game=run.game)
                    except Runs.DoesNotExist:
                        pass

        return super().formfield_for_foreignkey(db_field, request, **kwargs)  # type: ignore


class PlayersAdmin(admin.ModelAdmin):
    """Admin panel used with the `Players` model."""

    list_display = ["name", "user", "claim_status"]
    actions = ["update_player"]
    search_fields = ["name", "user__username"]

    @admin.action(description="Update Player Metadata")
    def update_player(
        self,
        _: HttpRequest,
        queryset: QuerySet["Players"],
    ) -> HttpResponse:
        """Updates the metadata for all selected players from the SRC API."""
        player_ids = [obj.id for obj in queryset]
        return redirect(
            reverse("admin:update_player") + f"?player_ids={','.join(player_ids)}"
        )

    def get_urls(
        self,
    ) -> list[URLPattern]:
        """Adds all above methods to custom URLs."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "update-player/",
                self.admin_site.admin_view(UpdatePlayerView.as_view()),
                name="update_player",
            ),
        ]
        return custom_urls + urls


admin.site.register(Games, GameAdmin)
admin.site.register(Awards, DefaultAdmin)


@admin.register(CountryCodes)
class CountryCodesAdmin(admin.ModelAdmin):
    list_display = ["name", "id", "flag"]
    search_fields = ["name"]
    fields = ["id", "name", "flag"]


admin.site.register(Categories, CategoriesAdmin)
admin.site.register(Levels, CategoriesAdmin)
admin.site.register(Variables, DefaultAdmin)
admin.site.register(VariableValues, VariableValuesAdmin)
admin.site.register(Runs, SpeedrunAdmin)
admin.site.register(Players, PlayersAdmin)
admin.site.register(Platforms, DefaultAdmin)
admin.site.register(NowStreaming)


class SRCSyncTaskAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "run",
        "action",
        "status",
        "moderator",
        "attempts",
        "created_at",
    ]
    list_filter = ["action", "status"]
    search_fields = ["run__id"]
    readonly_fields = ["created_at", "updated_at"]


admin.site.register(SRCSyncTask, SRCSyncTaskAdmin)
