# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Unit tests for the pure timeline resolver.

These tests build ScheduleSnapshot fixtures by hand so they exercise the
algorithm without touching the database.
"""

from __future__ import annotations

import datetime
import unittest

from cvat.apps.custom.scheduler.resolver import (
    ScheduleSnapshot,
    resolve_group_on,
)


def _snap(
    snapshot_id: int,
    start_date: datetime.date,
    sequence: tuple[str, ...],
    saved_at: datetime.datetime,
    is_deleted: bool = False,
) -> ScheduleSnapshot:
    return ScheduleSnapshot(
        id=snapshot_id,
        start_date=start_date,
        sequence=sequence,
        saved_at=saved_at,
        is_deleted=is_deleted,
    )


class ResolverTests(unittest.TestCase):
    def test_empty_list_returns_none(self):
        result = resolve_group_on([], datetime.date(2026, 6, 19))
        self.assertIsNone(result)

    def test_date_before_only_row_returns_none(self):
        row = _snap(
            1,
            datetime.date(2026, 6, 10),
            ("A", "B"),
            datetime.datetime(2026, 6, 1, 9, 0, 0),
        )
        self.assertIsNone(resolve_group_on([row], datetime.date(2026, 6, 9)))

    def test_date_on_start_returns_first_entry(self):
        row = _snap(
            1,
            datetime.date(2026, 6, 10),
            ("A", "B", "C"),
            datetime.datetime(2026, 6, 1, 9, 0, 0),
        )
        self.assertEqual(
            resolve_group_on([row], datetime.date(2026, 6, 10)),
            "A",
        )

    def test_modulo_wraps_around_cycle(self):
        row = _snap(
            1,
            datetime.date(2026, 6, 10),
            ("A", "B", "C"),
            datetime.datetime(2026, 6, 1, 9, 0, 0),
        )
        # Day 0 -> A, day 1 -> B, day 2 -> C, day 3 -> A.
        self.assertEqual(
            resolve_group_on([row], datetime.date(2026, 6, 13)),
            "A",
        )
        self.assertEqual(
            resolve_group_on([row], datetime.date(2026, 6, 14)),
            "B",
        )

    def test_two_row_timeline_picks_latest_start(self):
        older = _snap(
            1,
            datetime.date(2026, 1, 1),
            ("A", "B"),
            datetime.datetime(2026, 1, 1, 9, 0, 0),
        )
        newer = _snap(
            2,
            datetime.date(2026, 6, 1),
            ("X", "Y"),
            datetime.datetime(2026, 5, 28, 9, 0, 0),
        )
        # Before newer's start_date: older still applies.
        self.assertEqual(
            resolve_group_on([older, newer], datetime.date(2026, 5, 31)),
            # 150 days after Jan 1 = 150 % 2 = 0 -> A
            "A",
        )
        # On newer's start_date: newer's first entry wins.
        self.assertEqual(
            resolve_group_on([older, newer], datetime.date(2026, 6, 1)),
            "X",
        )

    def test_soft_deleted_row_is_ignored(self):
        deleted = _snap(
            1,
            datetime.date(2026, 6, 10),
            ("Z",),
            datetime.datetime(2026, 6, 1, 9, 0, 0),
            is_deleted=True,
        )
        active = _snap(
            2,
            datetime.date(2026, 6, 5),
            ("A", "B"),
            datetime.datetime(2026, 6, 4, 9, 0, 0),
        )
        # Deleted row has a later start_date but must be skipped.
        self.assertEqual(
            resolve_group_on([deleted, active], datetime.date(2026, 6, 12)),
            # 7 days after Jun 5: 7 % 2 = 1 -> B
            "B",
        )

    def test_same_start_date_latest_saved_at_wins(self):
        earlier = _snap(
            1,
            datetime.date(2026, 6, 1),
            ("OLD",),
            datetime.datetime(2026, 6, 1, 9, 0, 0),
        )
        later = _snap(
            2,
            datetime.date(2026, 6, 1),
            ("NEW",),
            datetime.datetime(2026, 6, 1, 18, 0, 0),
        )
        self.assertEqual(
            resolve_group_on([earlier, later], datetime.date(2026, 6, 1)),
            "NEW",
        )
