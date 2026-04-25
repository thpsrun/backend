from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, View

from srl.models import Categories, Games, Levels, Variables, VariableValues
from srl.srcom import sync_game, sync_game_runs, sync_obsolete_runs, sync_players


class UpdateGameView(ListView):
    """Updates all selected games, their metadata, categories, and variables from SRC's API."""

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        game_ids = request.GET.get("game_ids", "").split(",")
        for game_id in game_ids:
            sync_game.delay(game_id)

        return redirect("/illiad/srl/games/")


class RefreshGameRunsView(ListView):
    """Removes all games associated with the selected games to 'refresh' the leaderboard."""

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        game_ids = request.GET.get("game_ids", "").split(",")
        for game_id in game_ids:
            sync_game_runs.delay(game_id, 1)

        return redirect("/illiad/srl/games/")


class UpdateGameRunsView(ListView):
    """Updates all selected games, their metadata, categories, and variables from SRC's API."""

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        game_ids = request.GET.get("game_ids", "").split(",")
        for game_id in game_ids:
            sync_game_runs.delay(game_id, 0)

        return redirect("/illiad/srl/games/")


class UpdatePlayerView(ListView):
    """Updates all selected players and their metadata from SRC's API."""

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        player_ids = request.GET.get("player_ids", "").split(",")
        for player in player_ids:
            sync_players.delay(player)

        return redirect("/illiad/srl/players/")


class ImportObsoleteView(ListView):
    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        player_ids = request.GET.get("player_ids", "").split(",")
        for player in player_ids:
            sync_obsolete_runs(player)

        return redirect("/illiad/srl/players/")


class ManageMainVisibilityView(View):
    """Admin view to manage appear_on_main for categories and variable values per game."""

    def _build_context(
        self,
        game: Games,
    ) -> dict[str, Any]:
        """Build the tree of categories and their variable values for a game."""
        categories = (
            Categories.objects.filter(game=game)
            .order_by("name")
            .prefetch_related(
                "variables_set__variablevalues_set",
            )
        )

        categories_data: list[dict[str, Any]] = []
        for cat in categories:
            variable_values: list[dict[str, Any]] = []
            for var in cat.variables_set.all():  # type: ignore
                for vv in var.variablevalues_set.all():
                    variable_values.append(
                        {
                            "variable_name": var.name,
                            "value": vv,
                        }
                    )

            global_vars = Variables.objects.filter(
                game=game,
                cat__isnull=True,
                scope__in=["global", "full-game"],
            ).prefetch_related("variablevalues_set")

            for var in global_vars:
                for vv in var.variablevalues_set.all():  # type: ignore
                    if not any(
                        existing["value"].value == vv.value
                        for existing in variable_values
                    ):
                        variable_values.append(
                            {
                                "variable_name": f"{var.name} (global)",
                                "value": vv,
                            }
                        )

            categories_data.append(
                {
                    "category": cat,
                    "variable_values": variable_values,
                }
            )

        return {
            "game": game,
            "categories": categories_data,
            "title": f"Main Page Visibility: {game.name}",
            "opts": Games._meta,
            "has_view_permission": True,
        }

    def get(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        context = self._build_context(game)
        return render(request, "admin/srl/manage_main_visibility.html", context)

    def post(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)

        categories = Categories.objects.filter(game=game)
        for cat in categories:
            new_value = f"cat_{cat.id}" in request.POST
            if cat.appear_on_main != new_value:
                cat.appear_on_main = new_value
                cat.save(update_fields=["appear_on_main", "updated_at"])

        game_variable_values = VariableValues.objects.filter(
            var__game=game,
        )
        for vv in game_variable_values:
            new_value = f"vv_{vv.value}" in request.POST
            if vv.appear_on_main != new_value:
                vv.appear_on_main = new_value
                vv.save(update_fields=["appear_on_main", "updated_at"])

        messages.success(request, f"Main page visibility updated for {game.name}.")
        return redirect(
            request.path,
        )


class ManageOrderingView(View):
    """Admin view to manage sort ordering for full-game categories, levels, and variable values."""

    def _sorted_for_display(
        self,
        queryset,
    ) -> list:
        """Return items sorted: order>=1 first ascending, then order=0 alphabetically."""
        items = list(queryset)
        ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
        unordered = sorted([i for i in items if i.order == 0], key=lambda x: x.name)
        return ordered + unordered

    def _build_context(
        self,
        game: Games,
    ) -> dict[str, Any]:
        categories = self._sorted_for_display(
            Categories.objects.filter(game=game, type="per-game"),
        )
        levels = self._sorted_for_display(
            Levels.objects.filter(game=game),
        )
        variable_groups: list[dict[str, Any]] = []
        for var in (
            Variables.objects.filter(game=game)
            .order_by("name")
            .prefetch_related("variablevalues_set")
        ):
            vv_list = self._sorted_for_display(var.variablevalues_set.all())  # type: ignore
            if vv_list:
                variable_groups.append({"variable": var, "values": vv_list})

        return {
            "game": game,
            "categories": categories,
            "levels": levels,
            "variable_groups": variable_groups,
            "title": f"Manage Ordering: {game.name}",
            "opts": Games._meta,
            "has_view_permission": True,
        }

    def get(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        context = self._build_context(game)
        return render(request, "admin/srl/manage_ordering.html", context)

    def post(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        item_id = request.POST.get("item_id", "")
        direction = request.POST.get("direction", "")
        item_type = request.POST.get("item_type", "")

        if item_type == "category":
            queryset = Categories.objects.filter(game=game, type="per-game")
        elif item_type == "level":
            queryset = Levels.objects.filter(game=game)
        elif item_type == "variable_value":
            var_id = request.POST.get("var_id", "")
            if not var_id:
                messages.error(request, "Missing variable ID.")
                return redirect(request.path)
            queryset = VariableValues.objects.filter(var__game=game, var_id=var_id)
        else:
            messages.error(request, "Invalid item type.")
            return redirect(request.path)

        items = self._sorted_for_display(queryset)

        idx = next(
            (i for i, item in enumerate(items) if str(item.pk) == item_id),
            None,
        )
        if idx is None:
            messages.error(request, "Item not found.")
            return redirect(request.path)

        if direction == "up" and idx > 0:
            new_idx = idx - 1
        elif direction == "down" and idx < len(items) - 1:
            new_idx = idx + 1
        else:
            messages.warning(request, "Cannot move item in that direction.")
            return redirect(request.path)

        items[idx], items[new_idx] = items[new_idx], items[idx]

        for position, item in enumerate(items, start=1):
            if item.order != position:
                item.order = position
                item.save(update_fields=["order"])

        messages.success(request, "Order updated.")
        return redirect(request.path)
