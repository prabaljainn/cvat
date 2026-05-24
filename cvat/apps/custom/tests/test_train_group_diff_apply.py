from django.test import TestCase

from cvat.apps.custom.models import TrainGroupMapping
from cvat.apps.custom.train_group_parser import ParsedRow, compute_diff


class ComputeDiffTest(TestCase):
    def test_added_removed_changed_unchanged(self):
        # Seed current state
        TrainGroupMapping.objects.create(train_id="A1", group="X")  # changed → Y
        TrainGroupMapping.objects.create(train_id="A2", group="X")  # removed
        TrainGroupMapping.objects.create(train_id="A3", group="Y")  # unchanged

        new_rows = [
            ParsedRow("A1", "Y", line_no=2),  # changed
            ParsedRow("A3", "Y", line_no=3),  # unchanged
            ParsedRow("A4", "Z", line_no=4),  # added
        ]
        diff = compute_diff(new_rows, TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"], {
            "added": 1, "removed": 1, "changed": 1, "unchanged": 1,
        })
        self.assertEqual(diff["added"], [{"train_id": "A4", "group": "Z"}])
        self.assertEqual(diff["removed"], [{"train_id": "A2", "group": "X"}])
        self.assertEqual(diff["changed"], [{
            "train_id": "A1", "old_group": "X", "new_group": "Y",
        }])

    def test_diff_against_empty_current_state(self):
        new_rows = [ParsedRow("A1", "X", line_no=2)]
        diff = compute_diff(new_rows, TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"]["added"], 1)
        self.assertEqual(diff["counts"]["removed"], 0)

    def test_diff_clearing_all(self):
        TrainGroupMapping.objects.create(train_id="A1", group="X")
        TrainGroupMapping.objects.create(train_id="A2", group="Y")
        diff = compute_diff([], TrainGroupMapping.objects.all())
        self.assertEqual(diff["counts"]["removed"], 2)
        self.assertEqual(diff["counts"]["added"], 0)
