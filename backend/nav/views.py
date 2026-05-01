import json
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import View

from nav.models import NavItem


class ManageNavOrderingView(View):
    def _build_tree(
        self,
        items: list[NavItem],
        parent_id=None,
    ) -> list[dict[str, Any]]:
        children = sorted(
            [i for i in items if i.parent_id == parent_id],
            key=lambda x: (x.order if x.order > 0 else 9999, x.name),
        )
        return [
            {
                "item": child,
                "children": self._build_tree(items, child.pk),
            }
            for child in children
        ]

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        items = list(NavItem.objects.all())
        tree = self._build_tree(items, None)
        context = {
            "tree": tree,
            "title": "Manage Nav Ordering",
            "opts": NavItem._meta,
            "has_view_permission": True,
            "page_loaded_at": timezone.now().isoformat(),
        }
        return render(request, "admin/nav/manage_nav_ordering.html", context)


class NavReorderView(View):
    def post(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        item_id = request.POST.get("item_id", "")
        new_parent_id_raw = request.POST.get("new_parent_id", "")
        ordered_ids = request.POST.getlist("ordered_ids")

        if not ordered_ids:
            return HttpResponseBadRequest("ordered_ids is required")

        if new_parent_id_raw == "":
            new_parent_id = None
        else:
            try:
                new_parent_id = int(new_parent_id_raw)
            except ValueError:
                return HttpResponseBadRequest(
                    f"Invalid new_parent_id: {new_parent_id_raw!r}",
                )

        is_cross_parent = bool(item_id) and (
            self._current_parent_id(item_id) != new_parent_id
        )

        with transaction.atomic():
            if is_cross_parent:
                return self._handle_cross_parent(
                    item_id,
                    new_parent_id,
                    ordered_ids,
                )
            return self._handle_same_parent(
                new_parent_id,
                ordered_ids,
            )

    def _current_parent_id(
        self,
        item_id: str,
    ):
        try:
            return NavItem.objects.get(pk=item_id).parent_id
        except NavItem.DoesNotExist:
            return None

    def _handle_same_parent(
        self,
        parent_id,
        ordered_ids: list[str],
    ) -> HttpResponse:
        siblings_qs = NavItem.objects.filter(parent_id=parent_id).select_for_update()
        sib_map = {str(s.pk): s for s in siblings_qs}
        for sid in ordered_ids:
            if sid not in sib_map:
                return HttpResponseBadRequest(f"Unknown nav id: {sid}")

        for position, sid in enumerate(ordered_ids, start=1):
            item = sib_map[sid]
            if item.order != position:
                item.order = position
                item.save(update_fields=["order", "updated_at"])

        return self._success("Nav order updated.")

    def _handle_cross_parent(
        self,
        item_id: str,
        new_parent_id,
        ordered_ids: list[str],
    ) -> HttpResponse:
        try:
            item = NavItem.objects.select_for_update().get(pk=item_id)
        except NavItem.DoesNotExist:
            return HttpResponseBadRequest(f"Unknown nav id: {item_id}")
        old_parent_id = item.parent_id

        item.parent_id = new_parent_id
        item.save(update_fields=["parent_id", "updated_at"])

        dest_after_qs = NavItem.objects.filter(
            parent_id=new_parent_id
        ).select_for_update()
        dest_map = {str(s.pk): s for s in dest_after_qs}
        for sid in ordered_ids:
            if sid not in dest_map:
                return HttpResponseBadRequest(
                    f"Unknown nav id at destination: {sid}",
                )
        for position, sid in enumerate(ordered_ids, start=1):
            sib = dest_map[sid]
            if sib.order != position:
                sib.order = position
                sib.save(update_fields=["order", "updated_at"])

        source_remaining = list(
            NavItem.objects.filter(parent_id=old_parent_id)
            .order_by("order", "name")
            .select_for_update(),
        )
        for position, sib in enumerate(source_remaining, start=1):
            if sib.order != position:
                sib.order = position
                sib.save(update_fields=["order", "updated_at"])

        return self._success("Nav item moved.")

    def _success(
        self,
        message: str,
    ) -> HttpResponse:
        trigger = {
            "adminToast": {
                "kind": "success",
                "message": message,
            },
        }
        resp = HttpResponse("")
        resp["HX-Trigger"] = json.dumps(trigger)
        resp["X-New-Page-Loaded-At"] = timezone.now().isoformat()
        return resp
