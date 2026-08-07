# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Unit tests for the CSV-drop-group hook.

Exercises rewrite_schedule_for_removed_groups directly so the test does not
need to set up the full CSV upload path. The hook reads the latest
non-deleted TrainGroupSchedule and decides whether to append a new row.
"""

from __future__ import annotations

import datetime

from django.contrib.auth.models import User
from django.test import TestCase

from cvat.apps.custom.models import TrainGroupSchedule
from cvat.apps.custom.scheduler.csv_rewrite import rewrite_schedule_for_removed_groups
from cvat.apps.custom.scheduler.server_today import server_today


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

        result = rewrite_schedule_for_removed_groups(
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

    def test_future_dated_row_gets_corrected_row_with_same_start_date(self):
        future_start = server_today() + datetime.timedelta(days=5)
        TrainGroupSchedule.objects.create(
            start_date=future_start,
            sequence=["A", "B"],
            comment="future",
            saved_by=self.user,
            source="manual",
        )

        result = rewrite_schedule_for_removed_groups(
            removed_groups={"B"},
            user=self.user,
        )

        self.assertIsNone(result)
        corrected = TrainGroupSchedule.objects.get(source="csv_rewrite")
        # Same start_date: the corrected row shadows the stale one via
        # the saved_at tiebreak when its day arrives.
        self.assertEqual(corrected.start_date, future_start)
        self.assertEqual(corrected.sequence, ["A"])
        self.assertEqual(
            TrainGroupSchedule.objects.filter(is_deleted=False).count(), 2,
        )

    def test_row_starting_today_is_corrected_exactly_once(self):
        TrainGroupSchedule.objects.create(
            start_date=server_today(),
            sequence=["A", "B"],
            comment="today",
            saved_by=self.user,
            source="manual",
        )

        result = rewrite_schedule_for_removed_groups(
            removed_groups={"B"},
            user=self.user,
        )

        self.assertIsNone(result)
        # A row starting today is both the active row and a future row;
        # it must yield exactly one corrected row, not two.
        corrected = TrainGroupSchedule.objects.filter(source="csv_rewrite")
        self.assertEqual(corrected.count(), 1)
        self.assertEqual(corrected.get().sequence, ["A"])

    def test_drops_group_not_in_schedule_does_not_append(self):
        TrainGroupSchedule.objects.create(
            start_date=datetime.date.today() - datetime.timedelta(days=1),
            sequence=["A", "B"],
            comment="initial",
            saved_by=self.user,
            source="manual",
        )

        result = rewrite_schedule_for_removed_groups(
            removed_groups={"Z"},  # not referenced by any active schedule
            user=self.user,
        )

        self.assertIsNone(result)
        self.assertEqual(
            TrainGroupSchedule.objects.filter(is_deleted=False).count(),
            1,
        )
