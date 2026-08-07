# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Pure timeline resolution.

Given a flat list of schedule rows, return the group that is "active"
on a target date. This module has zero Django ORM imports so it can be
unit-tested without a database and reused by the views and the
csv-rewrite hook alike.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class ScheduleSnapshot:
    """A row pared down to just the fields the resolver needs.

    Using a dataclass (not the Django model) keeps the resolver free of
    ORM imports and trivially testable with hand-built fixtures.
    """

    id: int
    start_date: datetime.date
    sequence: tuple[str, ...]
    saved_at: datetime.datetime
    is_deleted: bool


def _pick_active_row(
    rows: Sequence[ScheduleSnapshot],
    target_date: datetime.date,
) -> Optional[ScheduleSnapshot]:
    """Return the row whose start_date is the latest <= target_date.

    Ties on start_date are broken by saved_at DESC so the most recently
    saved edit wins for the same effective day. Soft-deleted rows are
    skipped because they represent retracted history.
    """
    candidates = [
        r for r in rows
        if not r.is_deleted and r.start_date <= target_date
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (r.start_date, r.saved_at), reverse=True)
    return candidates[0]


def resolve_group_on(
    rows: Sequence[ScheduleSnapshot],
    target_date: datetime.date,
) -> Optional[str]:
    """Return the active group name on target_date, or None if undefined.

    Algorithm:
      1. Pick the schedule whose start_date is the latest <= target_date.
      2. days_since = (target_date - row.start_date).days
      3. Return row.sequence[days_since % len(sequence)]
    """
    row = _pick_active_row(rows, target_date)
    if row is None:
        return None
    if not row.sequence:
        # An empty sequence has no defined rotation. The serializer enforces
        # length >= 1 at write time, but a hand-rolled row (admin/shell/raw
        # migration) could slip through and would crash modulo. Treat as
        # "undefined" so the GET endpoint stays up.
        return None
    days_since = (target_date - row.start_date).days
    # Modulo with the sequence length implements the cycle wrap.
    return row.sequence[days_since % len(row.sequence)]
