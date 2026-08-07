# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""DRF serializers for TrainGroupSchedule.

Read serializer shapes the response payload. Write serializer enforces
the validation rules from the locked spec: start_date window, sequence
membership against the live TrainGroupMapping group set, and
whitespace-trimmed comment.
"""

from __future__ import annotations

import datetime

from rest_framework import serializers

from ..models import TrainGroupMapping, TrainGroupSchedule
from .constants import (
    MAX_COMMENT_LEN,
    MAX_FUTURE_DAYS,
    MAX_SEQUENCE_LEN,
    MIN_SEQUENCE_LEN,
)
from .server_today import server_today


class ScheduleRowSerializer(serializers.ModelSerializer):
    """Outbound shape of a single ScheduleRow."""

    saved_by_username = serializers.SerializerMethodField()
    saved_at = serializers.DateTimeField(
        format="%Y-%m-%dT%H:%M:%SZ",
        default_timezone=datetime.timezone.utc,
    )

    class Meta:
        model = TrainGroupSchedule
        fields = (
            "id",
            "start_date",
            "sequence",
            "comment",
            "saved_by_username",
            "saved_at",
            "source",
        )

    def get_saved_by_username(self, obj: TrainGroupSchedule) -> str | None:
        return obj.saved_by.username if obj.saved_by_id else None


def _known_groups() -> set[str]:
    """Distinct group names currently registered in TrainGroupMapping.

    Looked up per call rather than cached because the mapping can change
    between requests (CSV upload) and a schedule POST must validate
    against the freshest snapshot.
    """
    return set(TrainGroupMapping.objects.values_list("group", flat=True).distinct())


class ScheduleCreateSerializer(serializers.Serializer):
    """Inbound shape of a POST /schedule/ body.

    Returns a dict of cleaned values via validated_data; view layer is
    responsible for persisting the row. Errors are surfaced field-by-field
    so the view can flatten them into the {errors: [...]} response shape.
    """

    start_date = serializers.DateField()
    sequence = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        allow_empty=False,
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_COMMENT_LEN,
    )

    def validate_start_date(self, value: datetime.date) -> datetime.date:
        today = server_today()
        if value < today:
            raise serializers.ValidationError("start_date is in the past")
        if value > today + datetime.timedelta(days=MAX_FUTURE_DAYS):
            raise serializers.ValidationError(
                f"start_date is more than {MAX_FUTURE_DAYS} days in the future"
            )
        return value

    def validate_sequence(self, value: list[str]) -> list[str]:
        trimmed = [s.strip() for s in value]
        if any(s == "" for s in trimmed):
            raise serializers.ValidationError("sequence contains a blank entry")
        if not (MIN_SEQUENCE_LEN <= len(trimmed) <= MAX_SEQUENCE_LEN):
            raise serializers.ValidationError(
                f"sequence length must be between {MIN_SEQUENCE_LEN} and {MAX_SEQUENCE_LEN}"
            )
        known = _known_groups()
        unknown = [s for s in trimmed if s not in known]
        if unknown:
            # Surface every unknown entry at once so the operator can fix
            # all typos in a single retry instead of one per round-trip.
            raise serializers.ValidationError(
                f"sequence contains unknown groups: {sorted(set(unknown))}"
            )
        return trimmed

    def validate_comment(self, value: str) -> str:
        return value.strip()
