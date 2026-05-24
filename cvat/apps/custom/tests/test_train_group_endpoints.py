from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from cvat.apps.custom.models import TaskTrainMetadata, TrainGroupMapping


class MappingsListViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        TrainGroupMapping.objects.bulk_create([
            TrainGroupMapping(train_id="3101F", group="A"),
            TrainGroupMapping(train_id="3102F", group="B"),
            TrainGroupMapping(train_id="3103F", group="A"),
        ])

    def test_lists_all_mappings(self):
        resp = self.client.get("/api/custom/train-groups/mappings/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

    def test_filters_by_group(self):
        resp = self.client.get("/api/custom/train-groups/mappings/?group=A")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

    def test_searches_train_id(self):
        resp = self.client.get("/api/custom/train-groups/mappings/?search=3102")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.get("/api/custom/train-groups/mappings/")
        self.assertEqual(resp.status_code, 401)


class TemplateAndExportTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_template_returns_csv_with_header(self):
        resp = self.client.get("/api/custom/train-groups/mappings/template.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode()
        self.assertIn("train_id,group", body.splitlines()[0])

    def test_export_returns_current_mapping_as_csv(self):
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        TrainGroupMapping.objects.create(train_id="3102F", group="B")
        resp = self.client.get("/api/custom/train-groups/mappings/export.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode().splitlines()
        self.assertEqual(body[0], "train_id,group")
        self.assertIn("3101F,A", body)
        self.assertIn("3102F,B", body)


from io import BytesIO
from openpyxl import Workbook

from cvat.apps.custom.models import TrainGroupMappingVersion


def _make_admin():
    return User.objects.create_user("admin", password="pw", is_staff=True)


class UploadViewTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_csv_upload_creates_version_and_mapping(self):
        csv = b"train_id,group\n3101F,A\n3102F,B\n"
        resp = self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("schedule.csv", csv, content_type="text/csv"), "comment": "first"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["version"], 1)
        self.assertEqual(resp.data["diff"]["counts"]["added"], 2)
        self.assertEqual(TrainGroupMapping.objects.count(), 2)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "csv")
        self.assertTrue(v.is_current)

    def test_xlsx_upload_creates_version(self):
        wb = Workbook(); ws = wb.active
        ws.append(["train_id", "group"]); ws.append(["3101F", "A"])
        buf = BytesIO(); wb.save(buf)
        resp = self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("schedule.xlsx", buf.getvalue(),
                           content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "xlsx")

    def test_pasted_upload_json(self):
        resp = self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"text": "3101F\tA\n3102F\tB\n", "comment": "pasted"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        v = TrainGroupMappingVersion.objects.get(version_no=1)
        self.assertEqual(v.source_format, "paste")

    def test_dry_run_does_not_write(self):
        csv = b"train_id,group\n3101F,A\n"
        resp = self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("schedule.csv", csv, content_type="text/csv"), "dry_run": "true"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNone(resp.data["version"])
        self.assertEqual(TrainGroupMapping.objects.count(), 0)
        self.assertEqual(TrainGroupMappingVersion.objects.count(), 0)

    def test_invalid_csv_returns_400_no_writes(self):
        csv = b"train_id,group\n,A\n"
        resp = self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("bad.csv", csv, content_type="text/csv")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("errors", resp.data)
        self.assertEqual(TrainGroupMapping.objects.count(), 0)

    def test_non_admin_rejected(self):
        regular = User.objects.create_user("bob", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("x.csv", b"train_id,group\n", content_type="text/csv")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)


class VersionHistoryTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin2", password="pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        # Use the upload endpoint to create two versions
        self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("v1.csv", b"train_id,group\n3101F,A\n", content_type="text/csv")},
            format="multipart",
        )
        self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("v2.csv", b"train_id,group\n3101F,A\n3102F,B\n", content_type="text/csv"),
                  "comment": "added 3102F"},
            format="multipart",
        )

    def test_list_versions_descending(self):
        resp = self.client.get("/api/custom/train-groups/versions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["results"][0]["version_no"], 2)
        self.assertTrue(resp.data["results"][0]["is_current"])
        self.assertFalse(resp.data["results"][1]["is_current"])

    def test_detail_includes_csv_text_and_diff(self):
        resp = self.client.get("/api/custom/train-groups/versions/2/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csv_text", resp.data)
        self.assertIn("3101F,A", resp.data["csv_text"])
        self.assertEqual(resp.data["diff_summary"]["counts"]["added"], 1)

    def test_non_admin_rejected(self):
        regular = User.objects.create_user("eve", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.get("/api/custom/train-groups/versions/")
        self.assertEqual(resp.status_code, 403)


class RollbackTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin3", password="pw", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("v1.csv", b"train_id,group\n3101F,A\n", content_type="text/csv")},
            format="multipart",
        )
        self.client.post(
            "/api/custom/train-groups/mappings/upload/",
            data={"file": SimpleUploadedFile("v2.csv", b"train_id,group\n3102F,B\n", content_type="text/csv")},
            format="multipart",
        )

    def test_rollback_creates_new_version_with_old_mapping(self):
        resp = self.client.post(
            "/api/custom/train-groups/versions/1/rollback/",
            data={"comment": "back to v1"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["version"], 3)
        # Mapping is back to v1 state
        self.assertTrue(TrainGroupMapping.objects.filter(train_id="3101F", group="A").exists())
        self.assertFalse(TrainGroupMapping.objects.filter(train_id="3102F").exists())
        # New version row records source_version=1 and source_format=rollback
        v3 = TrainGroupMappingVersion.objects.get(version_no=3)
        self.assertEqual(v3.source_version_id, 1)
        self.assertEqual(v3.source_format, "rollback")
        self.assertTrue(v3.is_current)

    def test_rollback_nonexistent_version_404(self):
        resp = self.client.post("/api/custom/train-groups/versions/999/rollback/", format="json")
        self.assertEqual(resp.status_code, 404)

    def test_rollback_requires_admin(self):
        regular = User.objects.create_user("user1", password="pw")
        client = APIClient(); client.force_authenticate(regular)
        resp = client.post("/api/custom/train-groups/versions/1/rollback/", format="json")
        self.assertEqual(resp.status_code, 403)


from cvat.apps.engine.models import Task


class TasksPaginatedGroupFilterTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner")
        self.t1 = Task.objects.create(name="t1", owner=owner)
        self.t2 = Task.objects.create(name="t2", owner=owner)
        TaskTrainMetadata.objects.create(task=self.t1, train_id="3101F")
        TaskTrainMetadata.objects.create(task=self.t2, train_id="3199Z")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")

    def test_response_includes_group_field(self):
        resp = self.client.get("/api/custom/tasks-paginated/?include_analytics=false")
        self.assertEqual(resp.status_code, 200)
        groups_by_train = {
            r["train_metadata"]["train_id"]: r.get("group")
            for r in resp.data["results"]
        }
        self.assertEqual(groups_by_train["3101F"], "A")
        self.assertIsNone(groups_by_train["3199Z"])

    def test_filter_by_group(self):
        resp = self.client.get(
            "/api/custom/tasks-paginated/?include_analytics=false&group=A",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["train_metadata"]["train_id"], "3101F")

    def test_filter_ungrouped(self):
        resp = self.client.get(
            "/api/custom/tasks-paginated/?include_analytics=false&group=__ungrouped__",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["train_metadata"]["train_id"], "3199Z")


class TasksSummaryAvailableGroupsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u2", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner2")
        t1 = Task.objects.create(name="t1", owner=owner)
        t2 = Task.objects.create(name="t2", owner=owner)
        t3 = Task.objects.create(name="t3", owner=owner)
        TaskTrainMetadata.objects.create(task=t1, train_id="3101F")
        TaskTrainMetadata.objects.create(task=t2, train_id="3102F")
        TaskTrainMetadata.objects.create(task=t3, train_id="3103F")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")
        TrainGroupMapping.objects.create(train_id="3102F", group="A")
        TrainGroupMapping.objects.create(train_id="3103F", group="B")

    def test_available_groups_lists_groups_with_counts(self):
        resp = self.client.get("/api/custom/tasks-summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("available_groups", resp.data)
        by_name = {g["name"]: g["count"] for g in resp.data["available_groups"]}
        # Counts reflect mapped tasks regardless of filter
        self.assertEqual(by_name.get("A"), 2)
        self.assertEqual(by_name.get("B"), 1)


class ExtendedTaskGroupTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u3", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        owner = User.objects.create_user("owner3")
        self.t1 = Task.objects.create(name="t1", owner=owner)
        TaskTrainMetadata.objects.create(task=self.t1, train_id="3101F")
        TrainGroupMapping.objects.create(train_id="3101F", group="A")

    def test_detail_includes_group(self):
        resp = self.client.get(f"/api/custom/tasks-extended/{self.t1.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.get("group"), "A")
