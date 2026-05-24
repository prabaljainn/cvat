# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
Query helpers for annotating Task querysets with the train's group label.

Centralizes the JOIN so every view that exposes `group` uses the same
single-query pattern. Prevents N+1 regressions in the dashboard endpoints.
"""

from django.db.models import OuterRef, Subquery

from .models import TrainGroupMapping


UNGROUPED_SENTINEL = "__ungrouped__"


def annotate_train_group(queryset):
    """
    Annotate a Task queryset with a `train_group` attribute (string or None).

    Uses a correlated subquery on TrainGroupMapping; one SELECT regardless
    of result size.
    """
    sq = TrainGroupMapping.objects.filter(
        train_id=OuterRef("train_metadata__train_id"),
    ).values("group")[:1]
    return queryset.annotate(train_group=Subquery(sq))


def filter_by_group(queryset, group_param: str | None):
    """
    Apply `?group=...` filter (with `__ungrouped__` sentinel) to an
    already-annotated queryset.
    """
    if not group_param:
        return queryset
    group_param = group_param.strip()
    if group_param == UNGROUPED_SENTINEL:
        return queryset.filter(train_group__isnull=True)
    return queryset.filter(train_group=group_param)
