# Copyright (C) 2026 CVAT Custom - User Admin Console
# SPDX-License-Identifier: MIT

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import TestCase
from cvat.apps.custom.tests.json_client import JsonAPIClient

from cvat.apps.custom.models import UserAdminAuditLog

USERS_URL = "/api/custom/user-admin/users/"
AUDIT_URL = "/api/custom/user-admin/audit/"


def _make_admin(username="console_admin"):
    return User.objects.create_user(username, password="pw", is_staff=True)


class UserAdminPermissionTest(TestCase):
    def setUp(self):
        self.client = JsonAPIClient()

    def test_anonymous_gets_401(self):
        self.assertEqual(self.client.get(USERS_URL).status_code, 401)
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 401)

    def test_non_staff_gets_403_on_every_route(self):
        worker = User.objects.create_user("worker1", password="pw")
        target = User.objects.create_user("target1", password="pw")
        self.client.force_authenticate(worker)
        self.assertEqual(self.client.get(USERS_URL).status_code, 403)
        self.assertEqual(self.client.post(USERS_URL, {"username": "x"}).status_code, 403)
        self.assertEqual(
            self.client.patch(f"{USERS_URL}{target.id}/", {"role": "admin"}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"{USERS_URL}{target.id}/deactivate/").status_code, 403
        )
        self.assertEqual(
            self.client.post(f"{USERS_URL}{target.id}/reactivate/").status_code, 403
        )
        self.assertEqual(
            self.client.post(f"{USERS_URL}{target.id}/reset-password/").status_code, 403
        )
        self.assertEqual(self.client.get(AUDIT_URL).status_code, 403)


class UserAdminCrudTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = JsonAPIClient()
        self.client.force_authenticate(self.admin)

    def test_create_user_with_password_and_role(self):
        resp = self.client.post(
            USERS_URL,
            {
                "username": "reviewer1",
                "email": "reviewer1@example.com",
                "role": "user",
                "password": "s3cure-Pass-w0rd!",
            },
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["role"], "user")
        created = User.objects.get(username="reviewer1")
        self.assertTrue(created.check_password("s3cure-Pass-w0rd!"))
        self.assertTrue(created.groups.filter(name="user").exists())
        audit = UserAdminAuditLog.objects.get(action="create")
        self.assertEqual(audit.target_username, "reviewer1")
        self.assertEqual(audit.actor, self.admin)

    def test_create_admin_role_sets_staff_and_group(self):
        resp = self.client.post(
            USERS_URL,
            {"username": "admin2user", "email": "a2@example.com", "role": "admin"},
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        created = User.objects.get(username="admin2user")
        self.assertTrue(created.is_staff)
        self.assertTrue(created.groups.filter(name="admin").exists())
        # No password supplied: account exists but password is unusable
        # until the reset email flow sets one.
        self.assertFalse(created.has_usable_password())

    def test_create_duplicate_username_rejected(self):
        resp = self.client.post(USERS_URL, {"username": "console_admin"})
        self.assertEqual(resp.status_code, 400)

    def test_short_username_rejected(self):
        resp = self.client.post(USERS_URL, {"username": "abc"})
        self.assertEqual(resp.status_code, 400)

    def test_password_similar_to_username_rejected(self):
        resp = self.client.post(
            USERS_URL, {"username": "reviewer1", "password": "reviewer1"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_weak_password_rejected(self):
        resp = self.client.post(USERS_URL, {"username": "someone1", "password": "123"})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_role_rejected(self):
        resp = self.client.post(USERS_URL, {"username": "someone1", "role": "owner"})
        self.assertEqual(resp.status_code, 400)

    def test_patch_role_change_is_immediate(self):
        target = User.objects.create_user("promote_me", password="pw")
        resp = self.client.patch(f"{USERS_URL}{target.id}/", {"role": "admin"})
        self.assertEqual(resp.status_code, 200, resp.data)
        target.refresh_from_db()
        self.assertTrue(target.is_staff)
        self.assertEqual(resp.data["role"], "admin")
        audit = UserAdminAuditLog.objects.get(action="update")
        self.assertEqual(audit.changes, {"role": "admin"})

    def test_patch_same_role_writes_no_audit_row(self):
        target = User.objects.create_user("same_role", password="pw")
        resp = self.client.patch(f"{USERS_URL}{target.id}/", {"role": "user"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(UserAdminAuditLog.objects.filter(action="update").exists())

    def test_role_change_clears_other_iam_groups(self):
        worker_group, _ = Group.objects.get_or_create(name="worker")
        target = User.objects.create_user("ex_worker", password="pw")
        target.groups.add(worker_group)
        resp = self.client.patch(f"{USERS_URL}{target.id}/", {"role": "admin"})
        self.assertEqual(resp.status_code, 200)
        group_names = set(target.groups.values_list("name", flat=True))
        self.assertEqual(group_names, {"admin"})

    def test_cannot_demote_self(self):
        resp = self.client.patch(f"{USERS_URL}{self.admin.id}/", {"role": "user"})
        self.assertEqual(resp.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_cannot_demote_last_active_admin(self):
        other = _make_admin("second_admin")
        self.client.force_authenticate(other)
        # Deactivate console_admin so "other" becomes the last active admin.
        resp = self.client.post(f"{USERS_URL}{self.admin.id}/deactivate/")
        self.assertEqual(resp.status_code, 200)
        # Demoting the last active admin must be refused, even from a stale
        # admin session (simulated via force_authenticate).
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(f"{USERS_URL}{other.id}/", {"role": "user"})
        self.assertEqual(resp.status_code, 400)

    def test_patch_email_and_names(self):
        target = User.objects.create_user("rename_me", password="pw")
        resp = self.client.patch(
            f"{USERS_URL}{target.id}/",
            {"email": "new@example.com", "first_name": "Taro"},
        )
        self.assertEqual(resp.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.email, "new@example.com")
        self.assertEqual(target.first_name, "Taro")

    def test_patch_invalid_email_rejected(self):
        target = User.objects.create_user("bad_email", password="pw")
        resp = self.client.patch(f"{USERS_URL}{target.id}/", {"email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    def test_patch_oversize_name_rejected(self):
        target = User.objects.create_user("long_name", password="pw")
        resp = self.client.patch(f"{USERS_URL}{target.id}/", {"first_name": "x" * 300})
        self.assertEqual(resp.status_code, 400)

    def test_list_filters(self):
        User.objects.create_user("alice", email="alice@tokyu.co.jp", password="pw")
        inactive = User.objects.create_user("bobby", password="pw")
        inactive.is_active = False
        inactive.save()

        rows = lambda r: [u["username"] for u in r.data["results"]]
        self.assertEqual(rows(self.client.get(USERS_URL, {"search": "alice"})), ["alice"])
        self.assertEqual(
            rows(self.client.get(USERS_URL, {"search": "tokyu.co.jp"})), ["alice"]
        )
        self.assertEqual(
            rows(self.client.get(USERS_URL, {"role": "admin"})), ["console_admin"]
        )
        self.assertEqual(
            rows(self.client.get(USERS_URL, {"status": "inactive"})), ["bobby"]
        )


class UserAdminLifecycleTest(TestCase):
    def setUp(self):
        self.admin = _make_admin()
        self.client = JsonAPIClient()
        self.client.force_authenticate(self.admin)

    def test_deactivate_and_reactivate(self):
        target = User.objects.create_user("temp1", password="pw")
        resp = self.client.post(f"{USERS_URL}{target.id}/deactivate/")
        self.assertEqual(resp.status_code, 200, resp.data)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

        resp = self.client.post(f"{USERS_URL}{target.id}/reactivate/")
        self.assertEqual(resp.status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

        actions = list(
            UserAdminAuditLog.objects.order_by("id").values_list("action", flat=True)
        )
        self.assertEqual(actions, ["deactivate", "reactivate"])

    def test_cannot_deactivate_self(self):
        resp = self.client.post(f"{USERS_URL}{self.admin.id}/deactivate/")
        self.assertEqual(resp.status_code, 400)

    def test_cannot_deactivate_last_active_admin(self):
        other = _make_admin("second_admin")
        self.client.force_authenticate(other)
        resp = self.client.post(f"{USERS_URL}{self.admin.id}/deactivate/")
        self.assertEqual(resp.status_code, 200)
        # "other" is now the last active admin; even a stale admin session
        # (simulated via force_authenticate) must not deactivate it.
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"{USERS_URL}{other.id}/deactivate/")
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_sends_real_email_and_audits(self):
        target = User.objects.create_user(
            "resetme1", email="resetme@example.com", password="pw"
        )
        resp = self.client.post(f"{USERS_URL}{target.id}/reset-password/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(resp.data["email_sent"])
        # No mock: the locmem backend captures the actual message, proving
        # the form / template / URL chain works end to end.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("resetme@example.com", mail.outbox[0].to)
        audit = UserAdminAuditLog.objects.get(action="password_reset")
        self.assertEqual(audit.changes, {"email_sent": True})

    def test_reset_password_targets_only_the_managed_account(self):
        target = User.objects.create_user(
            "shared1", email="shared@example.com", password="pw"
        )
        User.objects.create_user("shared2", email="shared@example.com", password="pw")
        resp = self.client.post(f"{USERS_URL}{target.id}/reset-password/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_password_without_email_rejected(self):
        target = User.objects.create_user("noemail1", password="pw")
        resp = self.client.post(f"{USERS_URL}{target.id}/reset-password/")
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_for_deactivated_user_rejected(self):
        target = User.objects.create_user(
            "inactive1", email="i@example.com", password="pw"
        )
        target.is_active = False
        target.save()
        resp = self.client.post(f"{USERS_URL}{target.id}/reset-password/")
        self.assertEqual(resp.status_code, 400)

    def test_audit_list_filters(self):
        target = User.objects.create_user("audited1", password="pw")
        self.client.post(f"{USERS_URL}{target.id}/deactivate/")
        self.client.post(f"{USERS_URL}{target.id}/reactivate/")

        resp = self.client.get(AUDIT_URL, {"action": "deactivate"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["results"][0]["target_username"], "audited1")

        resp = self.client.get(AUDIT_URL, {"target_id": target.id})
        self.assertEqual(len(resp.data["results"]), 2)

        resp = self.client.get(AUDIT_URL, {"target_id": "abc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 0)
