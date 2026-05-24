from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase

from cvat.apps.custom.models import TrainGroupMapping, TrainGroupMappingVersion
from cvat.apps.custom.train_group_parser import ParsedRow, apply_upload, compute_diff


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


class ApplyUploadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice")

    def test_first_upload_creates_v1_and_populates_mapping(self):
        rows = [ParsedRow("A1", "X", 2), ParsedRow("A2", "Y", 3)]
        version = apply_upload(
            rows=rows, user=self.user, comment="initial",
            raw_input_text="train_id,group\nA1,X\nA2,Y\n",
            source_format="csv",
        )
        self.assertEqual(version.version_no, 1)
        self.assertTrue(version.is_current)
        self.assertEqual(version.source_format, "csv")
        self.assertEqual(version.row_count, 2)
        self.assertEqual(version.uploaded_by, self.user)
        self.assertEqual(TrainGroupMapping.objects.count(), 2)
        self.assertEqual(version.diff_summary["counts"]["added"], 2)

    def test_second_upload_bumps_version_and_replaces_mapping(self):
        apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="",
            raw_input_text="train_id,group\nA1,X\n", source_format="csv",
        )
        v2 = apply_upload(
            rows=[ParsedRow("A2", "Y", 2)], user=self.user, comment="",
            raw_input_text="train_id,group\nA2,Y\n", source_format="csv",
        )
        self.assertEqual(v2.version_no, 2)
        self.assertTrue(v2.is_current)

        # Only one is_current row
        self.assertEqual(
            TrainGroupMappingVersion.objects.filter(is_current=True).count(), 1,
        )
        # Mapping replaced: A1 gone, A2 present
        self.assertFalse(TrainGroupMapping.objects.filter(train_id="A1").exists())
        self.assertTrue(TrainGroupMapping.objects.filter(train_id="A2").exists())
        # Diff reflects swap
        self.assertEqual(v2.diff_summary["counts"]["added"], 1)
        self.assertEqual(v2.diff_summary["counts"]["removed"], 1)

    def test_source_version_recorded_on_rollback(self):
        v1 = apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="initial",
            raw_input_text="train_id,group\nA1,X\n", source_format="csv",
        )
        v2 = apply_upload(
            rows=[ParsedRow("A2", "Y", 2)], user=self.user, comment="oops",
            raw_input_text="train_id,group\nA2,Y\n", source_format="csv",
        )
        v3 = apply_upload(
            rows=[ParsedRow("A1", "X", 2)], user=self.user, comment="rollback to v1",
            raw_input_text="train_id,group\nA1,X\n",
            source_format="rollback", source_version=v1,
        )
        self.assertEqual(v3.source_version_id, v1.pk)
        # Past versions never mutated
        v1.refresh_from_db(); v2.refresh_from_db()
        self.assertFalse(v1.is_current)
        self.assertFalse(v2.is_current)
        self.assertTrue(v3.is_current)
