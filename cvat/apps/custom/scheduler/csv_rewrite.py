# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""CSV-drop-group hook.

When the train-group CSV upload removes a group from TrainGroupMapping
entirely, the active schedule or a future-dated schedule row may still
reference it. To keep the schedule consistent without mutating the
historical rows, we append new schedule rows whose sequences have the
removed groups filtered out.

The hook is called from views_train_groups.UploadView AFTER the upload
has been applied. It is best-effort and never raises through to the
caller because the CSV upload itself has already succeeded.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..models import TrainGroupSchedule
from .constants import (
    MAX_COMMENT_LEN,
    SOURCE_CSV_REWRITE,
    WARNING_SCHEDULE_WOULD_BE_EMPTY,
)
from .resolver import ScheduleSnapshot, _pick_active_row
from .server_today import server_today


def _latest_active_schedule() -> Optional[TrainGroupSchedule]:
    """Return the row whose start_date is the latest <= server_today.

    Delegates the "which row wins today" decision to the resolver so the
    resolution rule lives in exactly one place (resolver._pick_active_row).
    Iterates over the model's default ordering (Meta.ordering = (-start_date,
    -saved_at)), wraps each row in a ScheduleSnapshot, and lets the resolver
    apply the same algorithm the GET endpoint relies on.
    """
    rows = TrainGroupSchedule.objects.filter(is_deleted=False)
    snapshots = [
        ScheduleSnapshot(
            id=r.id,
            start_date=r.start_date,
            sequence=tuple(r.sequence or ()),
            saved_at=r.saved_at,
            is_deleted=r.is_deleted,
        )
        for r in rows
    ]
    picked = _pick_active_row(snapshots, server_today())
    if picked is None:
        return None
    # Re-fetch the concrete model row by id so callers can mutate / inspect
    # fields the snapshot does not carry (saved_by, comment, source).
    return TrainGroupSchedule.objects.filter(pk=picked.id).first()


def rewrite_schedule_for_removed_groups(
    *,
    removed_groups: Iterable[str],
    user,
) -> Optional[dict]:
    """Append corrected schedule rows when schedules reference removed groups.

    Two kinds of rows can reference a removed group:
      1. The currently-active row. Its correction is a new row starting
         today, so history before the upload stays intact.
      2. Any future-dated row (start_date >= today). Its correction is a
         new row with the SAME start_date; the resolver tiebreaks equal
         start_dates by saved_at DESC, so the newer corrected row shadows
         the stale one when its day arrives.

    Returns:
      - None when no rewrite was needed or every rewrite was appended
        successfully.
      - A single warning dict {code, message} when at least one rewrite
        would have produced an empty sequence (that row is kept as-is);
        the caller is expected to surface this in the upload response and
        NOT block the upload.
    """
    removed = {g for g in removed_groups if g}
    if not removed:
        return None

    today = server_today()

    # Collect (row, corrected start_date) pairs to process. Materialise
    # the future-row queryset BEFORE creating anything so the corrected
    # rows appended below are never themselves reprocessed.
    targets = []

    active = _latest_active_schedule()
    if active is not None:
        targets.append((active, today))
    active_id = active.id if active is not None else None

    future_rows = list(
        TrainGroupSchedule.objects.filter(is_deleted=False, start_date__gte=today)
    )
    for row in future_rows:
        # A row starting today is both the active row and a future row;
        # skip it here so it is corrected exactly once.
        if row.id == active_id:
            continue
        targets.append((row, row.start_date))

    warning: Optional[dict] = None
    for row, corrected_start_date in targets:
        sequence = list(row.sequence or [])
        if not any(g in removed for g in sequence):
            # No overlap with this row's cycle, so nothing to rewrite.
            continue

        # Preserve the original order; just drop the removed entries.
        new_sequence = [g for g in sequence if g not in removed]

        if not new_sequence:
            # An empty sequence is unrepresentable in the model and would
            # silently break the resolver. Keep the row as-is, surface one
            # warning, and let the operator pick a replacement manually.
            if warning is None:
                warning = {
                    "code": WARNING_SCHEDULE_WOULD_BE_EMPTY,
                    "message": (
                        "CSV upload would have left the active rotation empty; "
                        "the previous schedule was kept. Please save a new schedule."
                    ),
                }
            continue

        # Slice to the model's max_length: a large removed-group set can
        # overflow CharField(500) on Postgres (sqlite accepts it silently).
        comment = f"Auto-rewrite: CSV dropped {sorted(removed)}"[:MAX_COMMENT_LEN]
        TrainGroupSchedule.objects.create(
            start_date=corrected_start_date,
            sequence=new_sequence,
            comment=comment,
            saved_by=user,
            source=SOURCE_CSV_REWRITE,
        )
    return warning
