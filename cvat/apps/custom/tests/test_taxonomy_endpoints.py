# Copyright (C) 2026 CVAT Custom - Label Taxonomy
# SPDX-License-Identifier: MIT

from django.contrib.auth.models import User
from django.test import TestCase
from cvat.apps.custom.tests.json_client import JsonAPIClient

from cvat.apps.engine.models import Label, Project

from cvat.apps.custom.models import TaxonomyLabel

LABELS_URL = "/api/custom/taxonomy/labels/"
SYNC_URL = "/api/custom/taxonomy/sync/"


def _make_admin():
    return User.objects.create_user("tax_admin", password="pw", is_staff=True)


def _make_worker():
    return User.objects.create_user("tax_worker", password="pw")


class TaxonomyPermissionTest(TestCase):
    def setUp(self):
        self.client = JsonAPIClient()

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(LABELS_URL).status_code, 401)
        self.assertEqual(self.client.post(SYNC_URL, {}).status_code, 401)

    def test_non_staff_can_read_but_not_write(self):
        self.client.force_authenticate(_make_worker())
        self.assertEqual(self.client.get(LABELS_URL).status_code, 200)
        resp = self.client.post(LABELS_URL, {"name": "Crack"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.post(SYNC_URL, {"project_id": 1}).status_code, 403)

    def test_non_staff_cannot_patch_or_archive(self):
        entry = TaxonomyLabel.objects.create(name="Crack")
        self.client.force_authenticate(_make_worker())
        self.assertEqual(
            self.client.patch(f"{LABELS_URL}{entry.id}/", {"name": "X"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(f"{LABELS_URL}{entry.id}/archive/").status_code, 403
        )


class TaxonomyCrudTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = JsonAPIClient()
        self.client.force_authenticate(self.admin)

    def test_create_edit_and_ordering(self):
        resp = self.client.post(
            LABELS_URL,
            {"name": "Pantograph wear", "color": "#33DDFF", "category": "pantograph", "priority": 1},
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["color"], "#33ddff")
        self.assertEqual(resp.data["priority_display"], "High")
        self.assertEqual(resp.data["updated_by_username"], "tax_admin")

        entry_id = resp.data["id"]
        resp = self.client.patch(f"{LABELS_URL}{entry_id}/", {"name": "Pantograph crack"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["name"], "Pantograph crack")

    def test_duplicate_name_rejected(self):
        TaxonomyLabel.objects.create(name="Crack")
        resp = self.client.post(LABELS_URL, {"name": "Crack"})
        self.assertEqual(resp.status_code, 400)

    def test_bad_color_rejected(self):
        resp = self.client.post(LABELS_URL, {"name": "Crack", "color": "red"})
        self.assertEqual(resp.status_code, 400)

    def test_name_longer_than_cvat_label_cap_rejected(self):
        # engine.Label.name is capped at 64; anything longer would be
        # silently truncated on sync and corrupt name matching.
        resp = self.client.post(LABELS_URL, {"name": "x" * 65})
        self.assertEqual(resp.status_code, 400)

    def test_whitespace_padded_duplicate_rejected(self):
        TaxonomyLabel.objects.create(name="Crack")
        resp = self.client.post(LABELS_URL, {"name": " Crack "})
        self.assertEqual(resp.status_code, 400)

    def test_archive_restore_and_filters(self):
        crack = TaxonomyLabel.objects.create(name="Crack", category="body")
        TaxonomyLabel.objects.create(name="Rust", category="body")

        resp = self.client.post(f"{LABELS_URL}{crack.id}/archive/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["is_archived"])

        names = lambda r: [row["name"] for row in r.data["results"]]
        self.assertEqual(names(self.client.get(LABELS_URL, {"archived": "true"})), ["Crack"])
        self.assertEqual(names(self.client.get(LABELS_URL, {"archived": "false"})), ["Rust"])
        self.assertEqual(names(self.client.get(LABELS_URL, {"search": "rus"})), ["Rust"])
        self.assertEqual(len(names(self.client.get(LABELS_URL, {"category": "body"}))), 2)

        resp = self.client.post(f"{LABELS_URL}{crack.id}/restore/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["is_archived"])

    def test_no_delete_route(self):
        entry = TaxonomyLabel.objects.create(name="Crack")
        resp = self.client.delete(f"{LABELS_URL}{entry.id}/")
        self.assertEqual(resp.status_code, 405)


class TaxonomySyncTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = JsonAPIClient()
        self.client.force_authenticate(self.admin)
        self.project = Project.objects.create(name="Tokyu", owner=self.admin)

    def test_sync_requires_project_id(self):
        self.assertEqual(self.client.post(SYNC_URL, {}).status_code, 400)
        self.assertEqual(
            self.client.post(SYNC_URL, {"project_id": "abc"}).status_code, 400
        )

    def test_sync_reports_archived_label_still_present_in_project(self):
        Label.objects.create(project=self.project, name="Retired", color="#333333")
        TaxonomyLabel.objects.create(name="Retired", is_archived=True)
        resp = self.client.post(SYNC_URL, {"project_id": self.project.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["archived_but_present"], ["Retired"])
        self.assertEqual(resp.data["skipped_archived"], [])
        self.assertEqual(resp.data["unmanaged"], [])

    def test_sync_unknown_project_404(self):
        resp = self.client.post(SYNC_URL, {"project_id": 999999})
        self.assertEqual(resp.status_code, 404)

    def test_sync_creates_missing_skips_archived_reports_unmanaged(self):
        Label.objects.create(project=self.project, name="Legacy", color="#000000")
        TaxonomyLabel.objects.create(name="Crack", color="#ff0000")
        TaxonomyLabel.objects.create(name="Legacy", color="#111111")
        TaxonomyLabel.objects.create(name="Old defect", is_archived=True)

        resp = self.client.post(SYNC_URL, {"project_id": self.project.id})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["created"], ["Crack"])
        self.assertEqual(resp.data["already_present"], ["Legacy"])
        self.assertEqual(resp.data["skipped_archived"], ["Old defect"])
        self.assertEqual(resp.data["archived_but_present"], [])
        self.assertEqual(resp.data["unmanaged"], [])

        crack = Label.objects.get(project=self.project, name="Crack")
        self.assertEqual(crack.color, "#ff0000")
        # Existing CVAT label untouched.
        legacy = Label.objects.get(project=self.project, name="Legacy")
        self.assertEqual(legacy.color, "#000000")

    def test_sync_reports_unmanaged_cvat_labels(self):
        Label.objects.create(project=self.project, name="Handmade", color="#222222")
        resp = self.client.post(SYNC_URL, {"project_id": self.project.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["unmanaged"], ["Handmade"])

    def test_sync_is_idempotent(self):
        TaxonomyLabel.objects.create(name="Crack")
        first = self.client.post(SYNC_URL, {"project_id": self.project.id})
        second = self.client.post(SYNC_URL, {"project_id": self.project.id})
        self.assertEqual(first.data["created"], ["Crack"])
        self.assertEqual(second.data["created"], [])
        self.assertEqual(second.data["already_present"], ["Crack"])
        self.assertEqual(
            Label.objects.filter(project=self.project, name="Crack").count(), 1
        )
