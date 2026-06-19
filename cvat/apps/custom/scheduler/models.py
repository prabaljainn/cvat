# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""TrainGroupSchedule model.

One row per save. The full timeline is reconstructed at read time by
picking the row whose start_date is the latest <= a target date.
Editing history is preserved by never mutating existing rows; soft
delete hides a row without losing the audit trail.

The model is registered under app_label='custom' via re-export in
cvat/cvat/apps/custom/models.py because 'scheduler' is a sub-package,
not a separate Django app.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import models

from .constants import MAX_COMMENT_LEN, SOURCE_MANUAL


class TrainGroupSchedule(models.Model):
    """A single saved schedule entry on the rotation timeline."""

    # start_date is indexed because the resolver scans for the latest
    # row with start_date <= target_date on every read.
    start_date = models.DateField(db_index=True)

    # JSON list of group names that form the rotation. Stored as JSON
    # (not a comma string) so we never have to escape group names that
    # contain a comma.
    sequence = models.JSONField()

    comment = models.CharField(max_length=MAX_COMMENT_LEN, blank=True, default="")

    saved_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="train_group_schedules_saved",
    )

    # saved_at is the tiebreak when two rows share start_date; auto_now_add
    # plus db_index keeps the resolver's ORDER BY cheap.
    saved_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # 'manual' vs 'csv_rewrite' tells the UI whether a row was authored
    # by a human or appended by the CSV-drop hook.
    source = models.CharField(max_length=16, default=SOURCE_MANUAL)

    # Soft delete instead of hard delete so audit history is preserved
    # and so we can still answer "what was active on 2026-01-04?".
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="train_group_schedules_deleted",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "custom_train_group_schedule"
        indexes = [models.Index(fields=["is_deleted", "start_date"])]
        ordering = ["-start_date", "-saved_at"]

    def __str__(self) -> str:
        marker = " (deleted)" if self.is_deleted else ""
        return f"TrainGroupSchedule(start={self.start_date}, src={self.source}){marker}"
