# Copyright (C) 2026 CVAT Custom - Label Taxonomy
# SPDX-License-Identifier: MIT

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("custom", "0005_train_group_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="TaxonomyLabel",
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
                ("name", models.CharField(max_length=64, unique=True)),
                (
                    "color",
                    models.CharField(
                        default="#fa3253",
                        help_text=(
                            "Hex color in #rrggbb form, mirrored into the "
                            "CVAT label on sync."
                        ),
                        max_length=7,
                    ),
                ),
                ("category", models.CharField(blank=True, default="", max_length=100)),
                (
                    "priority",
                    models.IntegerField(
                        choices=[(1, "High"), (2, "Medium"), (3, "Low")], default=2
                    ),
                ),
                ("is_archived", models.BooleanField(default=False)),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="taxonomy_label_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Taxonomy Label",
                "verbose_name_plural": "Taxonomy Labels",
                "db_table": "custom_taxonomy_label",
                "ordering": ["priority", "name"],
            },
        ),
    ]
