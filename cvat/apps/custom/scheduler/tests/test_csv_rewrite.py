# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Unit tests for the CSV-drop-group hook.

Exercises maybe_rewrite_after_csv_upload directly so the test does not
need to set up the full CSV upload path. The hook reads the latest
non-deleted TrainGroupSchedule and decides whether to append a new row.
"""

from __future__ import annotations

import datetime

from django.contrib.auth.models import User
from django.test import TestCase

from cvat.apps.custom.models import TrainGroupSchedule
from cvat.apps.custom.scheduler.csv_rewrite import maybe_rewrite_after_csv_upload


class CsvRewriteHookTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")

    def test_drops_group_present_in_schedule_appends_new_row(self):
        TrainGroupSchedule.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=1),
            sequence=["A", "B", "C"],
            comment="initial",
            saved_by=self.user,
            source="manual",
        )

        result = maybe_rewrite_after_csv_upload(
            removed_groups={"B"},
            user=self.user,
        )

        # No warning means the rewrite was applied successfully.
        self.assertIsNone(result)
        rows = list(
            TrainGroupSchedule.objects.filter(is_deleted=False)
            .order_by("-saved_at")
        )
        self.assertEqual(len(rows), 2)
        latest = rows[0]
        self.assertEqual(latest.sequence, ["A", "C"])
        self.assertEqual(latest.source, "csv_rewrite")

    def test_drops_group_not_in_schedule_does_not_append(self):
        TrainGroupSchedule.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=1),
            sequence=["A", "B"],
            comment="initial",
            saved_by=self.user,
            source="manual",
        )

        result = maybe_rewrite_after_csv_upload(
            removed_groups={"Z"},  # not referenced by any active schedule
            user=self.user,
        )

        self.assertIsNone(result)
        self.assertEqual(
            TrainGroupSchedule.objects.filter(is_deleted=False).count(),
            1,
        )
