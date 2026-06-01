# Copyright (C) 2026 CVAT Custom Task Analysis Module
# SPDX-License-Identifier: MIT

"""
Real-DB tests for the grouped-query annotation analysis in the task-analysis view.

Unlike the pure ``test_annotation_stats`` tests, these exercise the actual ORM
queries (field paths, joins) against a database, and assert that the query count
does not scale with the number of labels (i.e. the old N+1 is gone).

Requires a test DB, so they run under ``manage.py test`` / CI, not the
boto3-only local venv.
"""

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from cvat.apps.engine.models import (
    Task, Segment, Job, Label,
    LabeledShape, LabeledImage, LabeledTrack, TrackedShape,
)
from cvat.apps.custom.views_task_analysis import TaskAnalysisView


class AnalyzeAnnotationsByLabelDBTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user("annotator", password="pw")
        self.task = Task.objects.create(name="t", owner=owner)
        segment = Segment.objects.create(task=self.task, start_frame=0, stop_frame=10)
        self.job = Job.objects.create(segment=segment)
        self.car = Label.objects.create(task=self.task, name="car", color="#f00")
        self.person = Label.objects.create(task=self.task, name="person", color="#0f0")
        self.view = TaskAnalysisView()

    def _shape(self, label, frame):
        return LabeledShape.objects.create(
            job=self.job, label=label, frame=frame, type="rectangle", points=[1, 2, 3, 4],
        )

    def _jobs(self):
        return Job.objects.filter(segment__task=self.task).select_related("segment")

    def test_matches_per_label_semantics(self):
        # car: shapes on 0, 0, 5 (3 rows, 2 distinct frames) + a tag on 7
        self._shape(self.car, 0)
        self._shape(self.car, 0)
        self._shape(self.car, 5)
        LabeledImage.objects.create(job=self.job, label=self.car, frame=7)
        # person: 1 shape on 3 + a track spanning frames 3 and 9
        self._shape(self.person, 3)
        track = LabeledTrack.objects.create(job=self.job, label=self.person, frame=3)
        TrackedShape.objects.create(track=track, frame=3, type="rectangle", points=[1, 2, 3, 4])
        TrackedShape.objects.create(
            track=track, frame=9, type="rectangle", points=[1, 2, 3, 4], outside=True
        )

        analysis = self.view._analyze_annotations_by_label(
            self.task, self._jobs(), [self.car, self.person]
        )

        car = analysis["labels_analysis"]["car"]
        self.assertEqual(car["annotated_frames"], [0, 5, 7])
        self.assertEqual(
            car["annotation_counts"], {"shapes": 3, "tracks": 0, "tags": 1, "total": 4}
        )

        person = analysis["labels_analysis"]["person"]
        self.assertEqual(person["annotated_frames"], [3, 9])
        self.assertEqual(
            person["annotation_counts"], {"shapes": 1, "tracks": 1, "tags": 0, "total": 2}
        )

        self.assertEqual(analysis["total_annotated_frames"], 5)

    def test_query_count_is_independent_of_label_count(self):
        def run():
            labels = list(Label.objects.filter(task=self.task))
            self.view._analyze_annotations_by_label(self.task, self._jobs(), labels)

        self._shape(self.car, 0)
        self._shape(self.person, 1)
        with CaptureQueriesContext(connection) as small:
            run()

        # Add many more labels + shapes; query count must stay flat.
        for i in range(10):
            label = Label.objects.create(task=self.task, name=f"extra_{i}", color="#fff")
            self._shape(label, i)
        with CaptureQueriesContext(connection) as large:
            run()

        self.assertEqual(len(large.captured_queries), len(small.captured_queries))
