from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from cvat.apps.custom.models import TrainGroupMapping


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
        resp = self.client.get("/api/train-groups/mappings/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 3)

    def test_filters_by_group(self):
        resp = self.client.get("/api/train-groups/mappings/?group=A")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

    def test_searches_train_id(self):
        resp = self.client.get("/api/train-groups/mappings/?search=3102")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.get("/api/train-groups/mappings/")
        self.assertEqual(resp.status_code, 401)
