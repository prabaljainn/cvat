# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""URL routes for the schedule sub-module.

Mounted by cvat/apps/custom/urls.py under train-groups/schedule/
so the public paths are:
  /api/custom/train-groups/schedule/
  /api/custom/train-groups/schedule/<id>/
"""

from __future__ import annotations

from django.urls import path

from .views import ScheduleDeleteView, ScheduleListCreateView

urlpatterns = [
    path(
        "",
        ScheduleListCreateView.as_view(),
        name="train-group-schedule-list-create",
    ),
    path(
        "<int:schedule_id>/",
        ScheduleDeleteView.as_view(),
        name="train-group-schedule-delete",
    ),
]
