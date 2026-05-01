import json
from datetime import datetime
from typing import Any

from django.db import models, transaction
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.generic import ListView, View

from srl.models import Categories, Games, Levels, Variables, VariableValues
from srl.srcom import sync_game, sync_game_runs, sync_obsolete_runs, sync_players


def _is_stale(
    request: HttpRequest,
    queryset,
) -> bool:
    raw = request.headers.get("X-Page-Loaded-At", "")
    if not raw:
        return False
    try:
        page_ts = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if page_ts.tzinfo is None:
        page_ts = timezone.make_aware(page_ts)
    latest = queryset.aggregate(latest=models.Max("updated_at"))["latest"]
    if latest is None:
        return False
    return latest > page_ts


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


class ManageGameDisplayView(View):
    def _sorted_for_display(
        self,
        queryset,
    ) -> list:
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
            .select_related("cat")
            .order_by("name")
            .prefetch_related("variablevalues_set")
        ):
            vv_list = self._sorted_for_display(var.variablevalues_set.all())  # type: ignore
            if vv_list:
                variable_groups.append({"variable": var, "values": vv_list})

        try:
            visibility_url = reverse("admin:srl_game_visibility", args=[game.id])
        except NoReverseMatch:
            visibility_url = ""

        return {
            "game": game,
            "categories": categories,
            "levels": levels,
            "variable_groups": variable_groups,
            "title": f"Manage Display: {game.name}",
            "opts": Games._meta,
            "has_view_permission": True,
            "page_loaded_at": timezone.now().isoformat(),
            "visibility_url": visibility_url,
        }

    def get(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        context = self._build_context(game)
        return render(request, "admin/srl/manage_game_display.html", context)


class GameReorderView(View):
    def post(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        scope = request.POST.get("scope", "")
        ordered_ids = request.POST.getlist("ordered_ids")
        var_id = request.POST.get("var_id", "")

        if scope == "category":
            queryset = Categories.objects.filter(game=game, type="per-game")
        elif scope == "level":
            queryset = Levels.objects.filter(game=game)
        elif scope == "variable_value":
            if not var_id:
                return HttpResponse(
                    "Missing var_id for variable_value scope.", status=400
                )
            queryset = VariableValues.objects.filter(var__game=game, var_id=var_id)
        else:
            return HttpResponse(f"Invalid scope: {scope!r}.", status=400)

        if _is_stale(request, queryset):
            return HttpResponse("Page data is stale. Reload and try again.", status=409)

        with transaction.atomic():
            list(queryset.select_for_update())
            now = timezone.now()
            for position, pk in enumerate(ordered_ids, start=1):
                queryset.filter(pk=pk).update(
                    order=position,
                    updated_at=now,
                )

        toast = {
            "adminToast": {
                "kind": "success",
                "message": f"Reordered {scope.replace('_', ' ')} successfully.",
            },
        }
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(toast)
        response["X-New-Page-Loaded-At"] = timezone.now().isoformat()
        return response


class GameVisibilityView(View):
    def post(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        game = get_object_or_404(Games, id=game_id)
        target_type = request.POST.get("target_type", "")
        target_id = request.POST.get("target_id", "")
        raw_value = request.POST.get("value", "false")
        value = raw_value.lower() in ("true", "1", "on", "yes")

        if target_type == "category":
            obj = get_object_or_404(Categories, id=target_id, game=game)
            stale_qs = Categories.objects.filter(id=target_id)
        elif target_type == "variable_value":
            obj = get_object_or_404(VariableValues, value=target_id, var__game=game)
            stale_qs = VariableValues.objects.filter(value=target_id)
        else:
            return HttpResponse(f"Invalid target_type: {target_type!r}.", status=400)

        if _is_stale(request, stale_qs):
            return HttpResponse("Page data is stale. Reload and try again.", status=409)

        obj.appear_on_main = value
        obj.save(update_fields=["appear_on_main", "updated_at"])

        toast = {
            "adminToast": {
                "kind": "success",
                "message": "Main page visibility updated.",
            },
        }
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(toast)
        response["X-New-Page-Loaded-At"] = timezone.now().isoformat()
        return response


class LegacyVisibilityRedirectView(View):
    def get(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        return HttpResponsePermanentRedirect(
            f"/illiad/srl/games/{game_id}/manage-display/",
        )


class LegacyOrderingRedirectView(View):
    def get(
        self,
        request: HttpRequest,
        game_id: str,
    ) -> HttpResponse:
        return HttpResponsePermanentRedirect(
            f"/illiad/srl/games/{game_id}/manage-display/",
        )
