# Copyright (C) 2026 CVAT Custom - User Admin Console
# SPDX-License-Identifier: MIT

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("custom", "0005_taxonomy_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAdminAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("target_username", models.CharField(max_length=150)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "Create"),
                            ("update", "Update"),
                            ("deactivate", "Deactivate"),
                            ("reactivate", "Reactivate"),
                            ("password_reset", "Password reset"),
                        ],
                        max_length=20,
                    ),
                ),
                ("changes", models.JSONField(blank=True, default=dict)),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="user_admin_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="user_admin_audit_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "User Admin Audit Log",
                "verbose_name_plural": "User Admin Audit Logs",
                "db_table": "custom_user_admin_audit",
                "ordering": ["-created_date", "-id"],
            },
        ),
    ]
