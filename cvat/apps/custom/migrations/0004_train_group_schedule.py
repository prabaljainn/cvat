# Generated for train_group_schedule

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("custom", "0003_tasktrainmetadata_server_files_path"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainGroupMapping",
            fields=[
                (
                    "train_id",
                    models.CharField(max_length=100, primary_key=True, serialize=False),
                ),
                ("group", models.CharField(db_index=True, max_length=50)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="train_group_mappings_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Train Group Mapping",
                "verbose_name_plural": "Train Group Mappings",
                "db_table": "custom_train_group_mapping",
            },
        ),
        migrations.AddIndex(
            model_name="traingroupmapping",
            index=models.Index(
                fields=["group", "train_id"],
                name="custom_trai_group_161b56_idx",
            ),
        ),
        migrations.CreateModel(
            name="TrainGroupMappingVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID",
                    ),
                ),
                ("version_no", models.PositiveIntegerField(unique=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.CharField(blank=True, max_length=500)),
                (
                    "csv_text",
                    models.TextField(help_text="Canonical CSV form (xlsx/paste uploads normalized to CSV)."),
                ),
                (
                    "source_format",
                    models.CharField(
                        default="csv",
                        help_text="One of: csv, xlsx, paste, rollback",
                        max_length=16,
                    ),
                ),
                ("row_count", models.PositiveIntegerField()),
                ("is_current", models.BooleanField(default=False)),
                (
                    "diff_summary",
                    models.JSONField(
                        default=dict,
                        help_text=(
                            "Pre-computed diff vs previous current version: "
                            "{added: [...], removed: [...], changed: [...], counts: {...}}"
                        ),
                    ),
                ),
                (
                    "source_version",
                    models.ForeignKey(
                        blank=True,
                        help_text="Set when this version was produced by rolling back to source_version.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rollbacks",
                        to="custom.traingroupmappingversion",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="train_group_mapping_versions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Train Group Mapping Version",
                "verbose_name_plural": "Train Group Mapping Versions",
                "db_table": "custom_train_group_mapping_version",
                "ordering": ["-version_no"],
            },
        ),
        migrations.AddConstraint(
            model_name="traingroupmappingversion",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_current", True)),
                fields=("is_current",),
                name="only_one_current_train_group_version",
            ),
        ),
    ]
