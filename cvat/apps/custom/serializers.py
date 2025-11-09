# Copyright (C) 2025 CVAT Custom Train Metadata Serializers
# SPDX-License-Identifier: MIT

"""
Custom serializers to extend CVAT Task API with train metadata.
"""

from rest_framework import serializers
from cvat.apps.engine.models import Task
from .models import TaskTrainMetadata, TaskComment
from django.contrib.auth.models import User


class TaskTrainMetadataSerializer(serializers.ModelSerializer):
    """Serializer for TaskTrainMetadata model."""

    verdict_display = serializers.CharField(source='get_verdict_display', read_only=True)

    class Meta:
        model = TaskTrainMetadata
        fields = [
            'train_id',
            'verdict',
            'verdict_display',
            'notes',
            'confidence_score',
            'server_files_path',
            'created_date',
            'updated_date'
        ]
        read_only_fields = ['created_date', 'updated_date', 'verdict_display']

    def validate_verdict(self, value):
        """Validate verdict choices."""
        if value not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
            raise serializers.ValidationError(
                f"Invalid verdict. Must be one of: {', '.join([choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices])}"
            )
        return value

    def validate_confidence_score(self, value):
        """Validate confidence score range."""
        if value is not None and not (0.0 <= value <= 1.0):
            raise serializers.ValidationError("Confidence score must be between 0.0 and 1.0")
        return value


class TaskWithTrainMetadataSerializer(serializers.ModelSerializer):
    """
    Extended Task serializer that includes train metadata.
    This can be used to extend the existing CVAT Task API.
    """

    train_metadata = TaskTrainMetadataSerializer(read_only=True)

    # Writable fields for train metadata
    train_id = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Train event identifier (defaults to task ID if not provided)"
    )
    verdict = serializers.ChoiceField(
        choices=TaskTrainMetadata.VerdictChoices.choices,
        required=False,
        default=TaskTrainMetadata.VerdictChoices.NOT_APPLICABLE,
        help_text="Train verdict: AC (Accepted), NA (Not Applicable), RJ (Rejected)"
    )
    train_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional notes about the train event"
    )
    confidence_score = serializers.FloatField(
        required=False,
        allow_null=True,
        min_value=0.0,
        max_value=1.0,
        help_text="Optional confidence score for the verdict (0.0 to 1.0)"
    )
    server_files_path = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=1024,
        help_text="S3 prefix or server files path used for this task's data source"
    )

    class Meta:
        model = Task
        fields = '__all__'  # Include all existing Task fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add train metadata fields to the existing Task fields
        if self.instance:
            # If we have an instance, populate train metadata fields
            try:
                train_metadata = self.instance.train_metadata
                self.fields['train_id'].initial = train_metadata.train_id
                self.fields['verdict'].initial = train_metadata.verdict
                self.fields['train_notes'].initial = train_metadata.notes
                self.fields['confidence_score'].initial = train_metadata.confidence_score
                self.fields['server_files_path'].initial = train_metadata.server_files_path
            except TaskTrainMetadata.DoesNotExist:
                # No train metadata exists yet, use defaults
                pass

    def create(self, validated_data):
        """Create task with train metadata."""
        # Extract train metadata fields
        train_data = self._extract_train_data(validated_data)

        # Create the task
        task = super().create(validated_data)

        # Create train metadata
        self._create_or_update_train_metadata(task, train_data)

        return task

    def update(self, instance, validated_data):
        """Update task with train metadata."""
        # Extract train metadata fields
        train_data = self._extract_train_data(validated_data)

        # Update the task
        task = super().update(instance, validated_data)

        # Update train metadata
        self._create_or_update_train_metadata(task, train_data)

        return task

    def _extract_train_data(self, validated_data):
        """Extract train metadata fields from validated data."""
        return {
            'train_id': validated_data.pop('train_id', None),
            'verdict': validated_data.pop('verdict', None),
            'notes': validated_data.pop('train_notes', None),
            'confidence_score': validated_data.pop('confidence_score', None),
            'server_files_path': validated_data.pop('server_files_path', None),
        }

    def _create_or_update_train_metadata(self, task, train_data):
        """Create or update train metadata for the task."""
        # Get or create train metadata
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        # Update fields if provided
        if train_data['train_id'] is not None:
            train_metadata.train_id = train_data['train_id'] or str(task.id)

        if train_data['verdict'] is not None:
            train_metadata.verdict = train_data['verdict']

        if train_data['notes'] is not None:
            train_metadata.notes = train_data['notes']

        if train_data['confidence_score'] is not None:
            train_metadata.confidence_score = train_data['confidence_score']

        if train_data['server_files_path'] is not None:
            train_metadata.server_files_path = train_data['server_files_path']

        train_metadata.save()
        return train_metadata

    def to_representation(self, instance):
        """Include train metadata in the serialized representation."""
        data = super().to_representation(instance)

        # Get or create train metadata
        try:
            train_metadata, created = TaskTrainMetadata.get_or_create_for_task(instance)
            data['train_metadata'] = TaskTrainMetadataSerializer(train_metadata).data

            # Also include train fields at the top level for easier UI access
            data['train_id'] = train_metadata.train_id
            data['verdict'] = train_metadata.verdict
            data['verdict_display'] = train_metadata.verdict_display
            data['train_notes'] = train_metadata.notes
            data['confidence_score'] = train_metadata.confidence_score
            data['server_files_path'] = train_metadata.server_files_path

        except Exception:
            # Fallback if train metadata can't be accessed
            data['train_metadata'] = None
            data['train_id'] = str(instance.id)
            data['verdict'] = TaskTrainMetadata.VerdictChoices.NOT_APPLICABLE
            data['verdict_display'] = 'Not Applicable'
            data['train_notes'] = None
            data['confidence_score'] = None
            data['server_files_path'] = None

        return data


# ==========================================
# Task Comment Serializers
# ==========================================

class TaskCommentAuthorSerializer(serializers.ModelSerializer):
    """Serializer for comment author information."""

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']
        read_only_fields = fields


class TaskCommentSerializer(serializers.ModelSerializer):
    """
    Serializer for TaskComment model with full details.

    Features:
    - Author information
    - Reply count and threading
    - Comment type display
    - Edit tracking
    """

    author = TaskCommentAuthorSerializer(read_only=True)
    author_id = serializers.IntegerField(write_only=True, required=False)

    # Display fields
    comment_type_display = serializers.CharField(source='get_comment_type_display', read_only=True)
    is_reply = serializers.BooleanField(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)

    # Nested replies (optional, can be heavy for deep threads)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = [
            'id', 'task', 'author', 'author_id', 'message',
            'comment_type', 'comment_type_display',
            'parent_comment', 'is_reply', 'reply_count',
            'created_date', 'updated_date', 'is_edited',
            'replies'
        ]
        read_only_fields = ['id', 'created_date', 'updated_date', 'is_edited']

    def get_replies(self, obj):
        """Get direct replies to this comment (not full thread)."""
        if hasattr(obj, '_prefetched_replies'):
            # Use prefetched data if available
            replies = obj._prefetched_replies
        else:
            # Limit to direct replies only to avoid deep recursion
            replies = obj.replies.all()[:10]  # Limit for performance

        return TaskCommentSimpleSerializer(replies, many=True).data

    def create(self, validated_data):
        # Set author from request user if not provided
        if 'author_id' not in validated_data:
            validated_data['author'] = self.context['request'].user
        else:
            validated_data['author_id'] = validated_data.pop('author_id')

        return super().create(validated_data)


class TaskCommentSimpleSerializer(serializers.ModelSerializer):
    """
    Simplified TaskComment serializer for nested use and lists.

    Avoids deep nesting and heavy queries for better performance.
    """

    author = TaskCommentAuthorSerializer(read_only=True)
    comment_type_display = serializers.CharField(source='get_comment_type_display', read_only=True)
    is_reply = serializers.BooleanField(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TaskComment
        fields = [
            'id', 'author', 'message',
            'comment_type', 'comment_type_display',
            'parent_comment', 'is_reply', 'reply_count',
            'created_date', 'updated_date', 'is_edited'
        ]
        read_only_fields = fields


class TaskCommentCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new task comments.

    Simplified for creation with validation.
    """

    class Meta:
        model = TaskComment
        fields = ['task', 'message', 'comment_type', 'parent_comment']

    def validate_parent_comment(self, value):
        """Ensure parent comment belongs to the same task."""
        if value and hasattr(self, 'initial_data') and 'task' in self.initial_data:
            task_id = self.initial_data['task']
            if value.task_id != task_id:
                raise serializers.ValidationError(
                    "Parent comment must belong to the same task."
                )
        return value

    def create(self, validated_data):
        # Set author from request user
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class TaskCommentUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating task comments.

    Only allows updating message and comment_type.
    """

    class Meta:
        model = TaskComment
        fields = ['message', 'comment_type']

    def update(self, instance, validated_data):
        # The model's save method will automatically set is_edited=True
        return super().update(instance, validated_data)
