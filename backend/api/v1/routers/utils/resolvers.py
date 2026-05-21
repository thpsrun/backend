from __future__ import annotations

import json
from typing import Any

from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from guides.models import Guides
from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels
from srl.models.runs import Runs
from srl.models.streaming import NowStreaming
from srl.models.variable_values import VariableValues
from srl.models.variables import Variables


def _path_kwargs(
    request: HttpRequest,
) -> dict[str, Any]:
    match = getattr(request, "resolver_match", None)
    return dict(match.kwargs) if match is not None else {}


def _json_body(
    request: HttpRequest,
) -> dict[str, Any]:
    cached = getattr(request, "_resolved_body_json", None)
    if isinstance(cached, dict):
        return cached
    raw = getattr(request, "body", b"") or b""
    if not raw:
        parsed: dict[str, Any] = {}
    else:
        try:
            loaded = json.loads(raw)
            parsed = loaded if isinstance(loaded, dict) else {}
        except (ValueError, TypeError):
            parsed = {}
    request._resolved_body_json = parsed  # type: ignore
    return parsed


def run_from_path(
    request: HttpRequest,
) -> Runs:
    kwargs = _path_kwargs(request)
    run_id = kwargs.get("run_id") or kwargs.get("id")
    if run_id is None:
        return None  # type: ignore
    return get_object_or_404(Runs, pk=run_id)


def game_from_path(
    request: HttpRequest,
) -> Games:
    # Order: explicit game_id > game_slug > id fallback.
    kwargs = _path_kwargs(request)
    if "game_id" in kwargs:
        return get_object_or_404(Games, pk=kwargs["game_id"])
    if "game_slug" in kwargs:
        return get_object_or_404(Games, slug=kwargs["game_slug"])
    if "id" in kwargs:
        ref = kwargs["id"]
        return get_object_or_404(Games, Q(pk=ref) | Q(slug=ref))
    return None  # type: ignore


def guide_from_path(
    request: HttpRequest,
) -> Guides:
    kwargs = _path_kwargs(request)
    if "slug" in kwargs:
        return get_object_or_404(Guides, slug=kwargs["slug"])
    if "guide_id" in kwargs:
        return get_object_or_404(Guides, pk=kwargs["guide_id"])
    return None  # type: ignore


def game_from_body(
    request: HttpRequest,
) -> Games | None:
    body = _json_body(request)
    game_ref = body.get("game_id") or body.get("game")
    if not game_ref:
        return None
    return Games.objects.filter(pk=game_ref).first()


def game_from_variable_body(
    request: HttpRequest,
) -> Games | None:
    body = _json_body(request)
    variable_ref = body.get("variable_id") or body.get("variable")
    if not variable_ref:
        return None
    variable = Variables.objects.filter(pk=variable_ref).select_related("game").first()
    return variable.game if variable else None


def game_from_category_path(
    request: HttpRequest,
) -> Games | None:
    kwargs = _path_kwargs(request)
    pk = kwargs.get("id") or kwargs.get("category_id")
    if pk is None:
        return None
    category = Categories.objects.filter(pk=pk).select_related("game").first()
    return category.game if category else None


def game_from_level_path(
    request: HttpRequest,
) -> Games | None:
    kwargs = _path_kwargs(request)
    pk = kwargs.get("id") or kwargs.get("level_id")
    if pk is None:
        return None
    level = Levels.objects.filter(pk=pk).select_related("game").first()
    return level.game if level else None


def game_from_variable_path(
    request: HttpRequest,
) -> Games | None:
    kwargs = _path_kwargs(request)
    pk = kwargs.get("id") or kwargs.get("variable_id")
    if pk is None:
        return None
    variable = Variables.objects.filter(pk=pk).select_related("game").first()
    return variable.game if variable else None


def game_from_variable_value_path(
    request: HttpRequest,
) -> Games | None:
    kwargs = _path_kwargs(request)
    pk = kwargs.get("value_id") or kwargs.get("id")
    if pk is None:
        return None
    value = VariableValues.objects.filter(pk=pk).select_related("var__game").first()
    return value.var.game if value and value.var else None


def game_from_stream_path(
    request: HttpRequest,
) -> Games | None:
    kwargs = _path_kwargs(request)
    player_id = kwargs.get("player_id")
    if player_id is None:
        return None
    stream = (
        NowStreaming.objects.filter(streamer_id=player_id)
        .select_related("game")
        .first()
    )
    return stream.game if stream else None


def resolve_game_or_none(
    game_id: str,
) -> Games | None:
    return Games.objects.filter(
        Q(id__iexact=game_id) | Q(slug__iexact=game_id),
    ).first()
