# Generated for the TrainGroupSchedule model (scheduler sub-package).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("custom", "0004_train_group_schedule"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainGroupSchedule",
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
                ("start_date", models.DateField(db_index=True)),
                ("sequence", models.JSONField()),
                ("comment", models.CharField(blank=True, default="", max_length=500)),
                ("saved_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("source", models.CharField(default="manual", max_length=16)),
                ("is_deleted", models.BooleanField(default=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "saved_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="train_group_schedules_saved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deleted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="train_group_schedules_deleted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "custom_train_group_schedule",
                "ordering": ["-start_date", "-saved_at"],
            },
        ),
        migrations.AddIndex(
            model_name="traingroupschedule",
            index=models.Index(
                fields=["is_deleted", "start_date"],
                name="custom_trai_is_dele_64c2d6_idx",
            ),
        ),
    ]
