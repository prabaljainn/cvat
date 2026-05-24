from django.contrib.auth.models import User
from django.test import TestCase

from cvat.apps.engine.models import Task
from cvat.apps.custom.models import TaskTrainMetadata, TrainGroupMapping
from cvat.apps.custom.train_group_query import annotate_train_group


class AnnotateTrainGroupTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user("owner")
        self.task_a = Task.objects.create(name="t_a", owner=owner)
        self.task_b = Task.objects.create(name="t_b", owner=owner)
        TaskTrainMetadata.objects.create(task=self.task_a, train_id="3101F")
        TaskTrainMetadata.objects.create(task=self.task_b, train_id="3199Z")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        # 3199Z deliberately unmapped

    def test_annotates_group_or_none(self):
        qs = annotate_train_group(Task.objects.all().order_by("id"))
        results = {t.id: t.train_group for t in qs}
        self.assertEqual(results[self.task_a.id], "A")
        self.assertIsNone(results[self.task_b.id])

    def test_single_query_no_n_plus_1(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            list(annotate_train_group(Task.objects.all().order_by("id")))
        # One SELECT — the Subquery is inlined; no N+1
        self.assertLessEqual(len(ctx.captured_queries), 2)
