# Copyright (C) 2026 CVAT Custom Task Analysis Module
# SPDX-License-Identifier: MIT

"""
Pure (Django-free) assembly of per-label annotation analysis.

The task-analysis view runs a constant number of grouped queries and hands the
raw ``(label_id, frame)`` rows to :func:`assemble_label_analysis`. Keeping the
computation here makes it unit-testable without a database and avoids the old
N+1 (one set of queries per job * label).
"""

from collections import defaultdict
from typing import Dict, Iterable, Mapping, Tuple


def assemble_label_analysis(
    labels: Iterable,
    shape_rows: Iterable[Tuple[int, int]],
    image_rows: Iterable[Tuple[int, int]],
    tracked_rows: Iterable[Tuple[int, int]],
    track_counts: Mapping[int, int],
) -> Dict:
    """
    Build the annotation analysis structure.

    Args:
        labels: objects exposing ``.id``, ``.name`` and ``.color``.
        shape_rows: ``(label_id, frame)`` for every LabeledShape across the jobs.
        image_rows: ``(label_id, frame)`` for every LabeledImage (tag).
        tracked_rows: ``(label_id, frame)`` for every TrackedShape (via track).
        track_counts: ``label_id -> number of tracks``.

    Returns:
        ``{"total_annotated_frames": int, "labels_analysis": {label_name: {...}}}``
        — identical in shape to the original per-label loop.
    """
    shape_frames, shape_count = _group_frames(shape_rows)
    image_frames, image_count = _group_frames(image_rows)
    tracked_frames, _ = _group_frames(tracked_rows)

    labels_analysis: Dict[str, Dict] = {}
    all_annotated_frames = set()

    for label in labels:
        frames = (
            shape_frames.get(label.id, set())
            | image_frames.get(label.id, set())
            | tracked_frames.get(label.id, set())
        )
        all_annotated_frames |= frames

        shapes = shape_count.get(label.id, 0)
        tags = image_count.get(label.id, 0)
        tracks = track_counts.get(label.id, 0)

        labels_analysis[label.name] = {
            "label_id": label.id,
            "label_name": label.name,
            "label_color": label.color,
            "annotated_frames": sorted(frames),
            "frame_count": len(frames),
            "annotation_counts": {
                "shapes": shapes,
                "tracks": tracks,
                "tags": tags,
                "total": shapes + tracks + tags,
            },
        }

    return {
        "total_annotated_frames": len(all_annotated_frames),
        "labels_analysis": labels_analysis,
    }


def _group_frames(rows: Iterable[Tuple[int, int]]):
    """Return ``(label_id -> set(frames), label_id -> row count)``."""
    frames = defaultdict(set)
    counts = defaultdict(int)
    for label_id, frame in rows:
        frames[label_id].add(frame)
        counts[label_id] += 1
    return frames, counts
