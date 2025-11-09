# Copyright (C) 2025 CVAT Custom Task Extension
# SPDX-License-Identifier: MIT

"""
Extended Task ViewSet and API views that include train metadata in CVAT's standard Task API.
"""

from django.http import Http404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.views import TaskViewSet as BaseTaskViewSet
from cvat.apps.engine.models import Task
from .serializers import TaskWithTrainMetadataSerializer, TaskTrainMetadataSerializer
from .models import TaskTrainMetadata


class ExtendedTaskViewSet(BaseTaskViewSet):
    """
    Extended Task ViewSet that includes train metadata in all CRUD operations.

    This extends CVAT's standard Task API to include train metadata fields:
    - train_id: Train event identifier
    - verdict: AC/NA/RJ verdict
    - train_notes: Optional notes
    - confidence_score: Optional confidence score

    All existing Task API functionality is preserved.
    """

    def get_serializer_class(self):
        """Use extended serializer that includes train metadata."""
        # Use our extended serializer for all operations
        return TaskWithTrainMetadataSerializer

    @action(detail=True, methods=['get', 'patch'], url_path='train-metadata')
    def train_metadata(self, request, pk=None):
        """
        Get or update train metadata for a specific task.

        GET /api/tasks/{id}/train-metadata/ - Get train metadata
        PATCH /api/tasks/{id}/train-metadata/ - Update train metadata
        """
        task = self.get_object()

        if request.method == 'GET':
            # Get train metadata
            train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)
            serializer = TaskTrainMetadataSerializer(train_metadata)
            return Response({
                'task_id': task.id,
                'task_name': task.name,
                'train_metadata': serializer.data,
                'is_new': created
            })

        elif request.method == 'PATCH':
            # Update train metadata
            train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)
            serializer = TaskTrainMetadataSerializer(
                train_metadata,
                data=request.data,
                partial=True
            )

            if serializer.is_valid():
                serializer.save()
                return Response({
                    'message': 'Train metadata updated successfully',
                    'task_id': task.id,
                    'task_name': task.name,
                    'train_metadata': serializer.data
                })
            else:
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )

    @action(detail=True, methods=['patch'], url_path='verdict')
    def update_verdict(self, request, pk=None):
        """
        Quick update of just the verdict for a task.

        PATCH /api/tasks/{id}/verdict/
        {
            "verdict": "AC"  // AC, NA, or RJ
        }
        """
        task = self.get_object()
        verdict = request.data.get('verdict')

        if not verdict:
            return Response(
                {'error': 'verdict is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate verdict
        verdict = verdict.upper()
        if verdict not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
            return Response(
                {'error': f'Invalid verdict. Must be one of: AC, NA, RJ'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update verdict
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)
        old_verdict = train_metadata.verdict
        train_metadata.verdict = verdict
        train_metadata.save()

        return Response({
            'message': f'Verdict updated from {old_verdict} to {verdict}',
            'task_id': task.id,
            'task_name': task.name,
            'train_id': train_metadata.train_id,
            'old_verdict': old_verdict,
            'new_verdict': verdict,
            'verdict_display': train_metadata.verdict_display
        })

    def list(self, request, *args, **kwargs):
        """Override list to include train metadata in task listings."""
        response = super().list(request, *args, **kwargs)

        # Add train metadata summary to the response
        if hasattr(response, 'data') and 'results' in response.data:
            # Add summary statistics
            total_tasks = len(response.data['results'])
            verdict_counts = {'AC': 0, 'NA': 0, 'RJ': 0}

            for task_data in response.data['results']:
                verdict = task_data.get('verdict', 'NA')
                if verdict in verdict_counts:
                    verdict_counts[verdict] += 1

            # Add metadata to response
            response.data['train_summary'] = {
                'total_tasks': total_tasks,
                'verdict_counts': verdict_counts,
                'has_train_metadata': True
            }

        return response

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to ensure train metadata is included."""
        response = super().retrieve(request, *args, **kwargs)

        # Train metadata is already included via the serializer
        # Just add a flag to indicate this is an extended response
        if hasattr(response, 'data'):
            response.data['has_train_metadata'] = True

        return response


@method_decorator(ensure_csrf_cookie, name='dispatch')
class TaskTrainMetadataAPIView(APIView):
    """
    Simple API view for task train metadata that can be easily integrated with UI.

    GET /api/custom/tasks/{id}/train-metadata/ - Get train metadata
    PATCH /api/custom/tasks/{id}/train-metadata/ - Update train metadata
    """

    permission_classes = [IsAuthenticated]

    def get_task(self, pk):
        """Get task by ID."""
        try:
            return Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            raise Http404("Task not found")

    def get(self, request, pk):
        """Get train metadata for a task."""
        task = self.get_task(pk)
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        return Response({
            'task_id': task.id,
            'task_name': task.name,
            'train_id': train_metadata.train_id,
            'verdict': train_metadata.verdict,
            'verdict_display': train_metadata.verdict_display,
            'notes': train_metadata.notes,
            'confidence_score': train_metadata.confidence_score,
            'server_files_path': train_metadata.server_files_path,
            'created_date': train_metadata.created_date.isoformat(),
            'updated_date': train_metadata.updated_date.isoformat(),
            'is_new': created
        })

    def patch(self, request, pk):
        """Update train metadata for a task."""
        task = self.get_task(pk)
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

        # Update fields if provided
        updated_fields = []

        if 'train_id' in request.data:
            train_metadata.train_id = request.data['train_id'] or str(task.id)
            updated_fields.append('train_id')

        if 'verdict' in request.data:
            verdict = request.data['verdict'].upper()
            if verdict not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
                return Response(
                    {'error': f'Invalid verdict. Must be one of: AC, NA, RJ'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            train_metadata.verdict = verdict
            updated_fields.append('verdict')

        if 'notes' in request.data:
            train_metadata.notes = request.data['notes']
            updated_fields.append('notes')

        if 'confidence_score' in request.data:
            try:
                confidence = float(request.data['confidence_score']) if request.data['confidence_score'] is not None else None
                if confidence is not None and not (0.0 <= confidence <= 1.0):
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

        if 'server_files_path' in request.data:
            train_metadata.server_files_path = request.data['server_files_path']
            updated_fields.append('server_files_path')

        train_metadata.save()

        return Response({
            'message': 'Train metadata updated successfully',
            'task_id': task.id,
            'task_name': task.name,
            'updated_fields': updated_fields,
            'train_id': train_metadata.train_id,
            'verdict': train_metadata.verdict,
            'verdict_display': train_metadata.verdict_display,
            'notes': train_metadata.notes,
            'confidence_score': train_metadata.confidence_score,
            'server_files_path': train_metadata.server_files_path,
            'updated_date': train_metadata.updated_date.isoformat()
        })


@method_decorator(ensure_csrf_cookie, name='dispatch')
class TaskVerdictUpdateAPIView(APIView):
    """
    Simple API view for quick verdict updates.

    PATCH /api/custom/tasks/{id}/verdict/
    {
        "verdict": "AC"  // AC, NA, or RJ
    }
    """

    permission_classes = [IsAuthenticated]

    def get_task(self, pk):
        """Get task by ID."""
        try:
            return Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            raise Http404("Task not found")

    def patch(self, request, pk):
        """Update verdict for a task."""
        task = self.get_task(pk)
        verdict = request.data.get('verdict')

        if not verdict:
            return Response(
                {'error': 'verdict is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate verdict
        verdict = verdict.upper()
        if verdict not in [choice[0] for choice in TaskTrainMetadata.VerdictChoices.choices]:
            return Response(
                {'error': f'Invalid verdict. Must be one of: AC (Accepted), NA (Not Applicable), RJ (Rejected)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update verdict
        train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)
        old_verdict = train_metadata.verdict
        train_metadata.verdict = verdict
        train_metadata.save()

        return Response({
            'message': f'Verdict updated from {old_verdict} to {verdict}',
            'task_id': task.id,
            'task_name': task.name,
            'train_id': train_metadata.train_id,
            'old_verdict': old_verdict,
            'new_verdict': verdict,
            'verdict_display': train_metadata.verdict_display,
            'updated_date': train_metadata.updated_date.isoformat()
        })
