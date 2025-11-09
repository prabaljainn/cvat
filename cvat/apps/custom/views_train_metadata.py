# Copyright (C) 2025 CVAT Custom Train Metadata API
# SPDX-License-Identifier: MIT

"""
Train Metadata Management API Views
"""

import json
from typing import Dict, Optional

from django.http import Http404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.models import Task
from .models import TaskTrainMetadata


class TrainMetadataView(APIView):
    """
    Manage train metadata for tasks.

    GET /api/custom/train-metadata/?task_id={id} - Get train metadata
    POST /api/custom/train-metadata/ - Create/Update train metadata
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get train metadata for a task."""
        task_id = request.query_params.get('task_id')

        if not task_id:
            return Response(
                {'error': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task_id = int(task_id)
        except ValueError:
            return Response(
                {'error': 'task_id must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the task
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get or create train metadata
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        return Response({
            "task_id": task.id,
            "task_name": task.name,
            "train_metadata": {
                "train_id": train_metadata.train_id,
                "verdict": train_metadata.verdict,
                "verdict_display": train_metadata.verdict_display,
                "notes": train_metadata.notes,
                "confidence_score": train_metadata.confidence_score,
                "server_files_path": train_metadata.server_files_path,
                "created_date": train_metadata.created_date.isoformat(),
                "updated_date": train_metadata.updated_date.isoformat(),
                "is_new": created
            }
        })

    def post(self, request):
        """Create or update train metadata for a task."""
        data = request.data

        # Validate required fields
        task_id = data.get('task_id')
        if not task_id:
            return Response(
                {'error': 'task_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task_id = int(task_id)
        except ValueError:
            return Response(
                {'error': 'task_id must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the task
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get or create train metadata
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        # Update fields if provided
        updated_fields = []

        if 'train_id' in data:
            train_metadata.train_id = data['train_id']
            updated_fields.append('train_id')

        if 'verdict' in data:
            verdict = data['verdict'].upper()
            if verdict not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
                return Response(
                    {'error': f'Invalid verdict. Must be one of: AC, NA, RJ'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            train_metadata.verdict = verdict
            updated_fields.append('verdict')

        if 'notes' in data:
            train_metadata.notes = data['notes']
            updated_fields.append('notes')

        if 'confidence_score' in data:
            try:
                confidence = float(data['confidence_score'])
                if not (0.0 <= confidence <= 1.0):
                    return Response(
                        {'error': 'confidence_score must be between 0.0 and 1.0'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                train_metadata.confidence_score = confidence
                updated_fields.append('confidence_score')
            except (ValueError, TypeError):
                return Response(
                    {'error': 'confidence_score must be a valid number'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if 'server_files_path' in data:
            train_metadata.server_files_path = data['server_files_path']
            updated_fields.append('server_files_path')

        # Save the metadata
        train_metadata.save()

        return Response({
            "message": "Train metadata updated successfully",
            "task_id": task.id,
            "task_name": task.name,
            "updated_fields": updated_fields,
            "train_metadata": {
                "train_id": train_metadata.train_id,
                "verdict": train_metadata.verdict,
                "verdict_display": train_metadata.verdict_display,
                "notes": train_metadata.notes,
                "confidence_score": train_metadata.confidence_score,
                "server_files_path": train_metadata.server_files_path,
                "created_date": train_metadata.created_date.isoformat(),
                "updated_date": train_metadata.updated_date.isoformat(),
                "was_created": created
            }
        })


class TrainVerdictUpdateView(APIView):
    """
    Quick API to update just the verdict for a task.

    POST /api/custom/update-verdict/
    {
        "task_id": 6,
        "verdict": "AC"  // AC, NA, or RJ
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Update verdict for a task."""
        data = request.data

        # Validate required fields
        task_id = data.get('task_id')
        verdict = data.get('verdict')

        if not task_id:
            return Response(
                {'error': 'task_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not verdict:
            return Response(
                {'error': 'verdict is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task_id = int(task_id)
        except ValueError:
            return Response(
                {'error': 'task_id must be an integer'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate verdict
        verdict = verdict.upper()
        if verdict not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
            return Response(
                {'error': f'Invalid verdict. Must be one of: AC (Accepted), NA (Not Applicable), RJ (Rejected)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the task
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get or create train metadata
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        # Update verdict
        old_verdict = train_metadata.verdict
        train_metadata.verdict = verdict
        train_metadata.save()

        return Response({
            "message": f"Verdict updated from {old_verdict} to {verdict}",
            "task_id": task.id,
            "task_name": task.name,
            "train_id": train_metadata.train_id,
            "old_verdict": old_verdict,
            "new_verdict": verdict,
            "verdict_display": train_metadata.verdict_display,
            "updated_date": train_metadata.updated_date.isoformat()
        })


class TrainMetadataListView(APIView):
    """
    List all tasks with their train metadata.

    GET /api/custom/train-metadata-list/
    Optional query parameters:
    - verdict: Filter by verdict (AC, NA, RJ)
    - project_id: Filter by project
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all tasks with train metadata."""

        # Get query parameters
        verdict_filter = request.query_params.get('verdict')
        project_id_filter = request.query_params.get('project_id')

        # Start with all tasks
        tasks = Task.objects.select_related('project', 'owner').all()

        # Apply project filter if specified
        if project_id_filter:
            try:
                project_id_filter = int(project_id_filter)
                tasks = tasks.filter(project_id=project_id_filter)
            except ValueError:
                return Response(
                    {'error': 'project_id must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Build response
        tasks_with_metadata = []

        for task in tasks:
            # Get or create train metadata
            train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

            # Apply verdict filter if specified
            if verdict_filter and train_metadata.verdict != verdict_filter.upper():
                continue

            task_info = {
                "task_id": task.id,
                "task_name": task.name,
                "project_id": task.project.id if task.project else None,
                "project_name": task.project.name if task.project else None,
                "owner": task.owner.username if task.owner else None,
                "status": task.status,
                "train_metadata": {
                    "train_id": train_metadata.train_id,
                    "verdict": train_metadata.verdict,
                    "verdict_display": train_metadata.verdict_display,
                    "notes": train_metadata.notes,
                    "confidence_score": train_metadata.confidence_score,
                    "server_files_path": train_metadata.server_files_path,
                    "created_date": train_metadata.created_date.isoformat(),
                    "updated_date": train_metadata.updated_date.isoformat()
                }
            }

            tasks_with_metadata.append(task_info)

        # Generate summary statistics
        total_tasks = len(tasks_with_metadata)
        verdict_counts = {}
        for choice in TaskTrainMetadata.VerdictChoices.choices:
            verdict_counts[choice[0]] = sum(1 for t in tasks_with_metadata
                                          if t['train_metadata']['verdict'] == choice[0])

        return Response({
            "total_tasks": total_tasks,
            "verdict_summary": {
                "AC": verdict_counts.get('AC', 0),
                "NA": verdict_counts.get('NA', 0),
                "RJ": verdict_counts.get('RJ', 0)
            },
            "filters_applied": {
                "verdict": verdict_filter,
                "project_id": project_id_filter
            },
            "tasks": tasks_with_metadata
        })
