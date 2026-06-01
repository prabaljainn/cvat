# Copyright (C) 2026 CVAT Custom Task Analysis Module
# SPDX-License-Identifier: MIT

"""
Tests for the pure label-analysis assembler used by the task-analysis endpoint.

Django-free: it operates on plain (label_id, frame) rows, so it runs under
``unittest`` with no test DB. The view feeds it the result of grouped queries.
"""

import unittest
from types import SimpleNamespace

from cvat.apps.custom.annotation_stats import assemble_label_analysis


def L(label_id, name, color="#fff"):
    return SimpleNamespace(id=label_id, name=name, color=color)


class AssembleLabelAnalysisTest(unittest.TestCase):
    def test_groups_frames_and_counts_per_label(self):
        labels = [L(1, "car", "#f00"), L(2, "person", "#0f0")]
        # car: shapes on frames 0,0,5 (3 rows, 2 distinct) + tag on 7
        # person: 1 shape on 3 + a track spanning frames 3,9
        shape_rows = [(1, 0), (1, 0), (1, 5), (2, 3)]
        image_rows = [(1, 7)]
        tracked_rows = [(2, 3), (2, 9)]
        track_counts = {2: 1}

        out = assemble_label_analysis(
            labels, shape_rows, image_rows, tracked_rows, track_counts
        )

        car = out["labels_analysis"]["car"]
        self.assertEqual(car["label_id"], 1)
        self.assertEqual(car["label_color"], "#f00")
        self.assertEqual(car["annotated_frames"], [0, 5, 7])
        self.assertEqual(car["frame_count"], 3)
        self.assertEqual(
            car["annotation_counts"],
            {"shapes": 3, "tracks": 0, "tags": 1, "total": 4},
        )

        person = out["labels_analysis"]["person"]
        self.assertEqual(person["annotated_frames"], [3, 9])
        self.assertEqual(
            person["annotation_counts"],
            {"shapes": 1, "tracks": 1, "tags": 0, "total": 2},
        )

        # union of {0,5,7} and {3,9} -> 5 distinct frames
        self.assertEqual(out["total_annotated_frames"], 5)

    def test_label_without_annotations_gets_zeroed_entry(self):
        out = assemble_label_analysis([L(1, "empty")], [], [], [], {})

        entry = out["labels_analysis"]["empty"]
        self.assertEqual(entry["annotated_frames"], [])
        self.assertEqual(entry["frame_count"], 0)
        self.assertEqual(
            entry["annotation_counts"],
            {"shapes": 0, "tracks": 0, "tags": 0, "total": 0},
        )
        self.assertEqual(out["total_annotated_frames"], 0)
