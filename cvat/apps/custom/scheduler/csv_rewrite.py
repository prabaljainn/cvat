# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""CSV-drop-group hook.

When the train-group CSV upload removes a group from TrainGroupMapping
entirely, the most recent active schedule may still reference it. To
keep the schedule consistent without mutating the historical row, we
append a new schedule row whose sequence has the removed groups
filtered out.

The hook is called from views_train_groups.UploadView AFTER the upload
has been applied. It is best-effort and never raises through to the
caller because the CSV upload itself has already succeeded.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..models import TrainGroupSchedule
from .constants import SOURCE_CSV_REWRITE, WARNING_SCHEDULE_WOULD_BE_EMPTY
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


def maybe_rewrite_after_csv_upload(
    *,
    removed_groups: Iterable[str],
    user,
) -> Optional[dict]:
    """Append a new schedule row if a current schedule references removed groups.

    Returns:
      - None when no rewrite was needed (no overlap, or no schedule exists).
      - A warning dict {code, message} when the rewrite would have produced
        an empty sequence; the caller is expected to surface this in the
        upload response and NOT block the upload.
      - None when the rewrite was appended successfully.

    The caller is responsible for collecting the warning and merging it
    into the existing warnings list on the upload response.
    """
    removed = {g for g in removed_groups if g}
    if not removed:
        return None

    latest = _latest_active_schedule()
    if latest is None:
        return None

    current_sequence = list(latest.sequence or [])
    if not any(g in removed for g in current_sequence):
        # No overlap with the live cycle, so nothing to rewrite.
        return None

    # Preserve the original order; just drop the removed entries.
    new_sequence = [g for g in current_sequence if g not in removed]

    if not new_sequence:
        # An empty sequence is unrepresentable in the model and would
        # silently break the resolver. Surface a warning and let the
        # operator pick a replacement manually.
        return {
            "code": WARNING_SCHEDULE_WOULD_BE_EMPTY,
            "message": (
                "CSV upload would have left the active rotation empty; "
                "the previous schedule was kept. Please save a new schedule."
            ),
        }

    TrainGroupSchedule.objects.create(
        start_date=server_today(),
        sequence=new_sequence,
        comment=f"Auto-rewrite: CSV dropped {sorted(removed)}",
        saved_by=user,
        source=SOURCE_CSV_REWRITE,
    )
    return None
