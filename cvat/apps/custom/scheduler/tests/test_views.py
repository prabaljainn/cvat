# Copyright (C) 2026 CVAT Custom - Train Group Schedule
# SPDX-License-Identifier: MIT

"""Integration tests for the schedule REST endpoints.

Uses Django TestCase + DRF APIClient to match the convention in
cvat/cvat/apps/custom/tests/.
"""

from __future__ import annotations

import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from cvat.apps.custom.models import TrainGroupMapping, TrainGroupSchedule
from cvat.apps.custom.scheduler.server_today import server_today


class ScheduleViewsTest(TestCase):
    def setUp(self):
        # Admin user so the POST and DELETE gates pass; the GET gate is
        # any authenticated user.
        self.admin = User.objects.create_user(
            "alice", password="pw", is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        # Validation requires the sequence entries to be members of the
        # live group set; seed a few groups so realistic payloads pass.
        TrainGroupMapping.objects.bulk_create([
            TrainGroupMapping(train_id="T1", group="A"),
            TrainGroupMapping(train_id="T2", group="B"),
            TrainGroupMapping(train_id="T3", group="C"),
        ])

    def _future_date_iso(self, days: int = 1) -> str:
        # Build the future date off server_today() (the same clock the
        # serializer compares against) so the test does not flake when the
        # machine TZ differs from SCHEDULE_TZ around midnight.
        return (server_today() + datetime.timedelta(days=days)).isoformat()

    def test_get_empty_returns_server_today_and_empty_list(self):
        resp = self.client.get("/api/custom/train-groups/schedule/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["schedules"], [])
        self.assertIn("server_today", resp.data)

    def test_post_creates_row_and_get_lists_it(self):
        payload = {
            "start_date": self._future_date_iso(2),
            "sequence": ["A", "B", "C"],
            "comment": "kickoff",
        }
        post_resp = self.client.post(
            "/api/custom/train-groups/schedule/",
            payload,
            format="json",
        )
        self.assertEqual(post_resp.status_code, 201, post_resp.data)
        self.assertEqual(post_resp.data["sequence"], ["A", "B", "C"])
        self.assertEqual(post_resp.data["source"], "manual")
        self.assertEqual(post_resp.data["saved_by_username"], "alice")

        get_resp = self.client.get("/api/custom/train-groups/schedule/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(len(get_resp.data["schedules"]), 1)

    def test_post_with_past_start_date_returns_400_with_field_errors(self):
        payload = {
            "start_date": "2000-01-01",
            "sequence": ["A"],
        }
        resp = self.client.post(
            "/api/custom/train-groups/schedule/",
            payload,
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("errors", resp.data)
        fields = {err["field"] for err in resp.data["errors"]}
        self.assertIn("start_date", fields)

    def test_delete_soft_deletes_and_repeat_returns_404(self):
        row = TrainGroupSchedule.objects.create(
            start_date=server_today() + datetime.timedelta(days=3),
            sequence=["A", "B"],
            comment="",
            saved_by=self.admin,
        )
        first = self.client.delete(
            f"/api/custom/train-groups/schedule/{row.id}/",
        )
        self.assertEqual(first.status_code, 204)
        row.refresh_from_db()
        self.assertTrue(row.is_deleted)

        # Already soft-deleted: a second delete must surface as 404
        # because the row is no longer visible to admin actions.
        second = self.client.delete(
            f"/api/custom/train-groups/schedule/{row.id}/",
        )
        self.assertEqual(second.status_code, 404)
