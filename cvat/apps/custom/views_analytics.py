# Copyright (C) 2025 CVAT Custom Analytics Module
# SPDX-License-Identifier: MIT

"""
Analytics and Reporting APIs for Train Metadata System
"""

from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from cvat.apps.engine.models import Task, Job, LabeledShape, LabeledImage, TrackedShape
from .models import TaskTrainMetadata


class TaskAnalyticsPagination(PageNumberPagination):
    """Custom pagination for task analytics."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TrainAnalyticsView(APIView):
    """
    Analytics API for train metadata with time-based filtering.

    GET /api/custom/train-analytics/?from_time=2025-01-01&to_time=2025-12-31

    Returns:
    - Total tasks count
    - AC (Accepted) tasks count
    - RJ (Rejected) tasks count
    - NA (Not Applicable) tasks count
    - Time-based filtering support
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get query parameters
        from_time = request.query_params.get('from_time')
        to_time = request.query_params.get('to_time')
        project_id = request.query_params.get('project_id')

        # Build base queryset
        tasks_queryset = Task.objects.all()

        # Apply project filter if specified
        if project_id:
            try:
                project_id = int(project_id)
                tasks_queryset = tasks_queryset.filter(project_id=project_id)
            except ValueError:
                return Response(
                    {'error': 'project_id must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Apply time filters if specified
        if from_time:
            try:
                from_datetime = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
                tasks_queryset = tasks_queryset.filter(created_date__gte=from_datetime)
            except ValueError:
                return Response(
                    {'error': 'Invalid from_time format. Use ISO format: 2025-01-01T00:00:00Z'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if to_time:
            try:
                to_datetime = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
                tasks_queryset = tasks_queryset.filter(created_date__lte=to_datetime)
            except ValueError:
                return Response(
                    {'error': 'Invalid to_time format. Use ISO format: 2025-12-31T23:59:59Z'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Get total tasks count
        total_tasks = tasks_queryset.count()

        # Get train metadata statistics
        # Create train metadata for tasks that don't have it
        task_ids = list(tasks_queryset.values_list('id', flat=True))
        existing_metadata_task_ids = set(
            TaskTrainMetadata.objects.filter(task_id__in=task_ids).values_list('task_id', flat=True)
        )

        # Create missing metadata
        tasks_without_metadata = tasks_queryset.exclude(id__in=existing_metadata_task_ids)
        for task in tasks_without_metadata:
            TaskTrainMetadata.get_or_create_for_task(task)

        # Now get the counts with proper train metadata
        metadata_queryset = TaskTrainMetadata.objects.filter(task__in=tasks_queryset)

        # Count by verdict
        verdict_counts = metadata_queryset.aggregate(
            ac_count=Count(Case(When(verdict='AC', then=1), output_field=IntegerField())),
            rj_count=Count(Case(When(verdict='RJ', then=1), output_field=IntegerField())),
            na_count=Count(Case(When(verdict='NA', then=1), output_field=IntegerField()))
        )

        # Calculate percentages
        ac_count = verdict_counts['ac_count'] or 0
        rj_count = verdict_counts['rj_count'] or 0
        na_count = verdict_counts['na_count'] or 0

        # Build response
        analytics = {
            "summary": {
                "total_tasks": total_tasks,
                "ac_tasks": ac_count,
                "rj_tasks": rj_count,
                "na_tasks": na_count,  # "Not Applicable" tasks
                "applicable_tasks": ac_count + rj_count  # Tasks with actual verdicts
            },
            "percentages": {
                "ac_percentage": round((ac_count / total_tasks * 100) if total_tasks > 0 else 0, 2),
                "rj_percentage": round((rj_count / total_tasks * 100) if total_tasks > 0 else 0, 2),
                "na_percentage": round((na_count / total_tasks * 100) if total_tasks > 0 else 0, 2),
                "applicable_percentage": round(((ac_count + rj_count) / total_tasks * 100) if total_tasks > 0 else 0, 2)
            },
            "filters_applied": {
                "from_time": from_time,
                "to_time": to_time,
                "project_id": project_id
            },
            "generated_at": timezone.now().isoformat()
        }

        return Response(analytics)


class TasksPaginatedView(APIView):
    """
    Paginated API for tasks with train metadata and annotation statistics.

    GET /api/custom/tasks-paginated/?page=1&page_size=20&verdict=AC&project_id=1

    Returns paginated list with:
    - Train metadata (train_id, verdict, notes, confidence_score)
    - Time data (created_date, updated_date)
    - Status (verdict display)
    - Annotation statistics (annotated frames / total frames)
    """

    permission_classes = [IsAuthenticated]
    pagination_class = TaskAnalyticsPagination

    def get(self, request):
        # Get query parameters
        verdict_filter = request.query_params.get('verdict')
        project_id_filter = request.query_params.get('project_id')
        search = request.query_params.get('search')

        # Build base queryset with optimizations
        queryset = Task.objects.select_related(
            'project', 'owner', 'assignee', 'data'
        ).prefetch_related(
            'train_metadata'
        ).all()

        # Apply filters
        if project_id_filter:
            try:
                project_id_filter = int(project_id_filter)
                queryset = queryset.filter(project_id=project_id_filter)
            except ValueError:
                return Response(
                    {'error': 'project_id must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(owner__username__icontains=search) |
                Q(project__name__icontains=search)
            )

        # Apply verdict filter (need to handle tasks without metadata)
        if verdict_filter:
            verdict_filter = verdict_filter.upper()
            if verdict_filter not in ['AC', 'NA', 'RJ']:
                return Response(
                    {'error': 'Invalid verdict. Must be AC, NA, or RJ'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get tasks with the specified verdict
            task_ids_with_verdict = TaskTrainMetadata.objects.filter(
                verdict=verdict_filter
            ).values_list('task_id', flat=True)

            if verdict_filter == 'NA':
                # For NA, also include tasks without metadata
                tasks_without_metadata = queryset.exclude(
                    id__in=TaskTrainMetadata.objects.values_list('task_id', flat=True)
                )
                queryset = queryset.filter(
                    Q(id__in=task_ids_with_verdict) | Q(id__in=tasks_without_metadata)
                )
            else:
                queryset = queryset.filter(id__in=task_ids_with_verdict)

        # Apply pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        if page is not None:
            # Build response data
            tasks_data = []
            for task in page:
                # Get or create train metadata
                train_metadata, created = TaskTrainMetadata.get_or_create_for_task(task)

                # Calculate annotation statistics
                annotation_stats = self._get_annotation_stats(task)

                task_data = {
                    "task_id": task.id,
                    "task_name": task.name,
                    "project_id": task.project.id if task.project else None,
                    "project_name": task.project.name if task.project else None,
                    "owner": task.owner.username if task.owner else None,
                    "assignee": task.assignee.username if task.assignee else None,
                    "status": task.status,

                    # Train metadata
                    "train_metadata": {
                        "train_id": train_metadata.train_id,
                        "verdict": train_metadata.verdict,
                        "verdict_display": train_metadata.verdict_display,
                        "notes": train_metadata.notes,
                        "confidence_score": train_metadata.confidence_score,
                        "created_date": train_metadata.created_date.isoformat(),
                        "updated_date": train_metadata.updated_date.isoformat()
                    },

                    # Time data
                    "time_data": {
                        "task_created": task.created_date.isoformat() if task.created_date else None,
                        "task_updated": task.updated_date.isoformat() if task.updated_date else None,
                        "metadata_created": train_metadata.created_date.isoformat(),
                        "metadata_updated": train_metadata.updated_date.isoformat()
                    },

                    # Annotation statistics
                    "annotation_stats": annotation_stats,

                    # Task data info
                    "task_info": {
                        "total_frames": task.data.size if task.data else 0,
                        "start_frame": task.data.start_frame if task.data else 0,
                        "stop_frame": task.data.stop_frame if task.data else 0,
                        "chunk_size": task.data.chunk_size if task.data else 0,
                        "image_quality": task.data.image_quality if task.data else 0
                    }
                }

                tasks_data.append(task_data)

            # Return paginated response
            return paginator.get_paginated_response(tasks_data)

        # Fallback if pagination fails
        return Response({"results": [], "count": 0})

    def _get_annotation_stats(self, task):
        """Calculate annotation statistics for a task."""

        # Get all jobs for this task
        jobs = Job.objects.filter(segment__task=task)

        # Get total frames
        total_frames = task.data.size if task.data else 0

        # Get annotated frames (unique frames with any annotation)
        annotated_frames = set()

        for job in jobs:
            # Frames with shapes
            shape_frames = LabeledShape.objects.filter(job=job).values_list('frame', flat=True)
            annotated_frames.update(shape_frames)

            # Frames with tags
            image_frames = LabeledImage.objects.filter(job=job).values_list('frame', flat=True)
            annotated_frames.update(image_frames)

            # Frames with tracks
            tracked_frames = TrackedShape.objects.filter(track__job=job).values_list('frame', flat=True)
            annotated_frames.update(tracked_frames)

        annotated_count = len(annotated_frames)

        # Calculate annotation density
        annotation_density = (annotated_count / total_frames * 100) if total_frames > 0 else 0

        return {
            "total_frames": total_frames,
            "annotated_frames": annotated_count,
            "unannotated_frames": total_frames - annotated_count,
            "annotation_density_percentage": round(annotation_density, 2),
            "annotation_status": self._get_annotation_status(annotation_density)
        }

    def _get_annotation_status(self, density):
        """Get human-readable annotation status based on density."""
        if density == 0:
            return "Not Started"
        elif density < 25:
            return "In Progress (Low)"
        elif density < 75:
            return "In Progress (Medium)"
        elif density < 100:
            return "In Progress (High)"
        else:
            return "Complete"


class TasksQuickStatsView(APIView):
    """
    Quick statistics API for dashboard widgets.

    GET /api/custom/tasks-quick-stats/

    Returns quick stats without heavy computation:
    - Task counts by verdict
    - Recent activity
    - Top projects
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get basic counts
        total_tasks = Task.objects.count()

        # Get verdict counts (create metadata if needed)
        verdict_counts = TaskTrainMetadata.objects.aggregate(
            ac_count=Count(Case(When(verdict='AC', then=1), output_field=IntegerField())),
            rj_count=Count(Case(When(verdict='RJ', then=1), output_field=IntegerField())),
            na_count=Count(Case(When(verdict='NA', then=1), output_field=IntegerField()))
        )

        # Tasks without metadata count as NA
        tasks_with_metadata = TaskTrainMetadata.objects.count()
        tasks_without_metadata = total_tasks - tasks_with_metadata
        na_count = (verdict_counts['na_count'] or 0) + tasks_without_metadata

        # Recent activity (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_tasks = Task.objects.filter(created_date__gte=week_ago).count()
        recent_updates = TaskTrainMetadata.objects.filter(updated_date__gte=week_ago).count()

        # Top projects by task count
        top_projects = Task.objects.filter(project__isnull=False).values(
            'project__id', 'project__name'
        ).annotate(
            task_count=Count('id')
        ).order_by('-task_count')[:5]

        stats = {
            "summary": {
                "total_tasks": total_tasks,
                "ac_tasks": verdict_counts['ac_count'] or 0,
                "rj_tasks": verdict_counts['rj_count'] or 0,
                "na_tasks": na_count,
                "tasks_with_metadata": tasks_with_metadata
            },
            "recent_activity": {
                "new_tasks_last_week": recent_tasks,
                "metadata_updates_last_week": recent_updates
            },
            "top_projects": [
                {
                    "project_id": proj['project__id'],
                    "project_name": proj['project__name'],
                    "task_count": proj['task_count']
                }
                for proj in top_projects
            ],
            "generated_at": timezone.now().isoformat()
        }

        return Response(stats)
