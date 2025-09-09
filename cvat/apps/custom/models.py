# Copyright (C) 2025 CVAT Custom Train Metadata Module
# SPDX-License-Identifier: MIT

"""
Custom models to extend CVAT functionality with train event metadata.
"""

from django.db import models
from cvat.apps.engine.models import Task


class TaskTrainMetadata(models.Model):
    """
    Extended metadata for tasks to associate them with train events.

    This model extends the Task functionality without modifying the core CVAT models.
    Each task can have associated train metadata including train_id and verdict.
    """

    class VerdictChoices(models.TextChoices):
        ACCEPTED = 'AC', 'Accepted'
        NOT_APPLICABLE = 'NA', 'Not Applicable'
        REJECTED = 'RJ', 'Rejected'

    # One-to-one relationship with Task
    task = models.OneToOneField(
        Task,
        on_delete=models.CASCADE,
        related_name='train_metadata',
        help_text="Associated CVAT task"
    )

    # Train ID - defaults to task ID if not specified
    train_id = models.CharField(
        max_length=100,
        help_text="Train event identifier (defaults to task ID)"
    )

    # Verdict with enum choices
    verdict = models.CharField(
        max_length=2,
        choices=VerdictChoices.choices,
        default=VerdictChoices.NOT_APPLICABLE,
        help_text="Train verdict: AC (Accepted), NA (Not Applicable), RJ (Rejected)"
    )

    # Metadata timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    # Optional additional fields for future extensibility
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Optional notes about the train event"
    )

    confidence_score = models.FloatField(
        blank=True,
        null=True,
        help_text="Optional confidence score for the verdict (0.0 to 1.0)"
    )

    class Meta:
        verbose_name = "Task Train Metadata"
        verbose_name_plural = "Task Train Metadata"
        db_table = "custom_task_train_metadata"

    def __str__(self):
        return f"Train {self.train_id} - Task {self.task.id} ({self.get_verdict_display()})"

    def save(self, *args, **kwargs):
        # Auto-set train_id to task ID if not provided
        if not self.train_id:
            self.train_id = str(self.task.id)
        super().save(*args, **kwargs)

    @property
    def verdict_display(self):
        """Human-readable verdict display."""
        return self.get_verdict_display()

    @classmethod
    def get_or_create_for_task(cls, task):
        """
        Get or create train metadata for a task.
        Creates with default values if it doesn't exist.
        """
        metadata, created = cls.objects.get_or_create(
            task=task,
            defaults={
                'train_id': str(task.id),
                'verdict': cls.VerdictChoices.NOT_APPLICABLE
            }
        )
        return metadata, created
