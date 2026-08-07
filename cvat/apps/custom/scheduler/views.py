# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""DRF views for the train-group schedule API.

  GET    /api/custom/train-groups/schedule/        - list non-deleted rows
  POST   /api/custom/train-groups/schedule/        - create a new row
  DELETE /api/custom/train-groups/schedule/<id>/   - soft delete a row

Permissions:
  GET  any authenticated user (read-only consumers, e.g. CVAT runners).
  POST and DELETE require MAPPING_ADMIN_PERMISSIONS, the same gate used
  by the train-group CSV upload, so a single role change moves both.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import TrainGroupSchedule
from ..views_train_groups import MAPPING_ADMIN_PERMISSIONS
from .constants import DEDUPE_WINDOW_SECONDS, SOURCE_MANUAL
from .serializers import ScheduleCreateSerializer, ScheduleRowSerializer
from .server_today import server_today_iso


def _flatten_drf_errors(detail) -> list[dict]:
    """Convert DRF's nested error dict into the spec's flat list shape.

    Spec: {errors: [{field, reason}]}. DRF gives us
    {field: [ErrorDetail, ...]} or nested variants; flatten to one
    {field, reason} per message so the UI can render them as a list.
    """
    flat: list[dict] = []
    if isinstance(detail, dict):
        for field, value in detail.items():
            if isinstance(value, list):
                for item in value:
                    flat.append({"field": field, "reason": str(item)})
            else:
                flat.append({"field": field, "reason": str(value)})
    elif isinstance(detail, list):
        for item in detail:
            flat.append({"field": "non_field_errors", "reason": str(item)})
    else:
        flat.append({"field": "non_field_errors", "reason": str(detail)})
    return flat


class ScheduleListCreateView(APIView):
    """GET and POST on /api/custom/train-groups/schedule/."""

    # filter_backends opt-out matches the pattern in views_train_groups;
    # CVAT's IAM-aware filter chain otherwise interferes with schema gen.
    filter_backends: list = []

    def get_permissions(self):
        # Read is open to any authenticated user; writes are admin-only.
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [p() for p in MAPPING_ADMIN_PERMISSIONS]

    def get(self, request):
        # Ordering is enforced by TrainGroupSchedule.Meta.ordering
        # (-start_date, -saved_at). Keeping the model as the single source of
        # truth so a future tweak to resolution priority does not silently
        # drift away from the GET payload.
        rows = (
            TrainGroupSchedule.objects
            .filter(is_deleted=False)
            .select_related("saved_by")
        )
        return Response({
            "schedules": ScheduleRowSerializer(rows, many=True).data,
            "server_today": server_today_iso(),
        })

    def post(self, request):
        serializer = ScheduleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": _flatten_drf_errors(serializer.errors)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cleaned = serializer.validated_data
        start_date: datetime.date = cleaned["start_date"]
        sequence: list[str] = cleaned["sequence"]
        comment: str = cleaned.get("comment", "")

        # Dedupe an accidental double-submit: an identical save within the
        # dedupe window returns the existing row with 200 instead of
        # creating a duplicate. We wrap the SELECT and CREATE in a single
        # atomic block with select_for_update() over candidates so two
        # concurrent identical POSTs serialize: the second blocks until
        # the first commits and then finds the existing row.
        window_start = timezone.now() - datetime.timedelta(seconds=DEDUPE_WINDOW_SECONDS)
        with transaction.atomic():
            # Filter by the cheap indexed columns only and compare the
            # sequence in Python. JSONField text-equality semantics differ
            # across DB backends (Postgres jsonb is value-equal; SQLite
            # JSONField compares text and is whitespace-sensitive); a
            # Python-side comparison of the materialised list sidesteps
            # backend-specific JSON encoding.
            candidates = list(
                TrainGroupSchedule.objects
                .select_for_update()
                .filter(
                    is_deleted=False,
                    start_date=start_date,
                    saved_at__gte=window_start,
                )
                .order_by("-saved_at")
            )
            existing = next(
                (
                    row for row in candidates
                    if list(row.sequence or []) == list(sequence)
                ),
                None,
            )
            if existing is not None:
                return Response(
                    ScheduleRowSerializer(existing).data,
                    status=status.HTTP_200_OK,
                )

            row = TrainGroupSchedule.objects.create(
                start_date=start_date,
                sequence=sequence,
                comment=comment,
                saved_by=request.user if request.user.is_authenticated else None,
                source=SOURCE_MANUAL,
            )
        return Response(
            ScheduleRowSerializer(row).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduleDeleteView(APIView):
    """DELETE /api/custom/train-groups/schedule/<id>/."""

    permission_classes = MAPPING_ADMIN_PERMISSIONS
    filter_backends: list = []

    def delete(self, request, schedule_id: int):
        try:
            row = TrainGroupSchedule.objects.get(
                pk=schedule_id,
                is_deleted=False,
            )
        except TrainGroupSchedule.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        row.is_deleted = True
        row.deleted_at = timezone.now()
        row.deleted_by = request.user if request.user.is_authenticated else None
        row.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])
        return Response(status=status.HTTP_204_NO_CONTENT)
