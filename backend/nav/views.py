from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from nav.models import NavItem


def sorted_for_display(
    queryset,
) -> list:
    """Return items sorted: order>=1 first ascending, then order=0 alphabetically."""
    items = list(queryset)
    ordered = sorted([i for i in items if i.order > 0], key=lambda x: x.order)
    unordered = sorted([i for i in items if i.order == 0], key=lambda x: x.name)
    return ordered + unordered


class ManageNavOrderingView(View):
    """Admin view to manage sort ordering for nav items."""

    def _build_context(self) -> dict[str, Any]:
        """Build context with top-level items and their children grouped."""
        top_level = sorted_for_display(
            NavItem.objects.filter(parent__isnull=True),
        )
        groups: list[dict[str, Any]] = []
        for item in top_level:
            children_qs = sorted_for_display(
                NavItem.objects.filter(parent=item),
            )
            children: list[dict[str, Any]] = []
            for child in children_qs:
                grandchildren_qs = sorted_for_display(
                    NavItem.objects.filter(parent=child),
                )
                grandchildren: list[dict[str, Any]] = []
                for gc in grandchildren_qs:
                    great_grandchildren = sorted_for_display(
                        NavItem.objects.filter(parent=gc),
                    )
                    grandchildren.append(
                        {
                            "item": gc,
                            "great_grandchildren": great_grandchildren,
                        }
                    )
                children.append(
                    {
                        "item": child,
                        "grandchildren": grandchildren,
                    }
                )
            groups.append(
                {
                    "item": item,
                    "children": children,
                }
            )

        return {
            "top_level": top_level,
            "groups": groups,
            "title": "Manage Nav Ordering",
            "opts": NavItem._meta,
            "has_view_permission": True,
        }

    def get(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        context = self._build_context()
        return render(request, "admin/nav/manage_nav_ordering.html", context)

    def post(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        item_id = request.POST.get("item_id", "")
        direction = request.POST.get("direction", "")
        parent_id = request.POST.get("parent_id", "")

        if parent_id == "":
            queryset = NavItem.objects.filter(parent__isnull=True)
        else:
            parent = get_object_or_404(NavItem, pk=parent_id)
            queryset = NavItem.objects.filter(parent=parent)

        items = sorted_for_display(queryset)

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
                item.save(update_fields=["order", "updated_at"])

        messages.success(request, "Order updated.")
        return redirect(request.path)
