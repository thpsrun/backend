from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import ListView

from srl.srcom import sync_game, sync_game_runs, sync_players


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
