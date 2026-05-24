# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
Query helpers for annotating Task querysets with the train's group label.

Centralizes the JOIN so every view that exposes `group` uses the same
single-query pattern. Prevents N+1 regressions in the dashboard endpoints.
"""

from django.db.models import OuterRef, Subquery

from .models import TaskTrainMetadata, TrainGroupMapping


UNGROUPED_SENTINEL = "__ungrouped__"


def annotate_train_group(queryset):
    """
    Annotate a Task queryset with a `train_group` attribute (string or None).

    Two annotations chained on the OUTER queryset:
      1) _train_id  = subquery on TaskTrainMetadata WHERE task_id = Task.pk
      2) train_group = subquery on TrainGroupMapping WHERE train_id = _train_id

    Why this shape: we can't put the second subquery INSIDE the first
    (`filter(train_id=Subquery(...))`) because that nests OuterRef one
    level deeper, and `OuterRef("pk")` in a nested context refers to the
    *immediate* parent subquery — which is TrainGroupMapping. Because
    TrainGroupMapping has `train_id` as its primary key, the inner
    OuterRef("pk") resolves to a varchar `train_id` instead of Task.id
    (integer), causing a Postgres "operator does not exist: integer =
    character varying" error.

    Chaining annotations on the OUTER queryset keeps both subqueries at
    the same depth — each one's OuterRef refers directly to a Task column.
    """
    queryset = queryset.annotate(
        _train_id=Subquery(
            TaskTrainMetadata.objects
            .filter(task_id=OuterRef("pk"))
            .values("train_id")[:1]
        )
    )
    return queryset.annotate(
        train_group=Subquery(
            TrainGroupMapping.objects
            .filter(train_id=OuterRef("_train_id"))
            .values("group")[:1]
        )
    )


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
