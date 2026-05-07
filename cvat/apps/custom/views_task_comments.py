# Copyright (C) 2025 CVAT Custom Task Comments Module
# SPDX-License-Identifier: MIT

"""
Task Comments API Views

Provides CRUD operations for task-level comments with threading support.
Unlike CVAT's Issue-based comments, these are directly attached to tasks.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404

from cvat.apps.engine.models import Task
from .models import TaskComment
from .serializers import (
    TaskCommentSerializer,
    TaskCommentSimpleSerializer,
    TaskCommentCreateSerializer,
    TaskCommentUpdateSerializer
)


class TaskCommentViewSet(viewsets.ModelViewSet):
    iam_supports_organization_params = True
    """
    ViewSet for Task Comments with full CRUD operations.

    Features:
    - List comments for a task
    - Create new comments and replies
    - Update existing comments (author only)
    - Delete comments (author only)
    - Threading support
    - Pagination

    Endpoints:
    - GET /api/custom/tasks/{task_id}/comments/ - List comments
    - POST /api/custom/tasks/{task_id}/comments/ - Create comment
    - GET /api/custom/comments/{id}/ - Get comment details
    - PATCH /api/custom/comments/{id}/ - Update comment
    - DELETE /api/custom/comments/{id}/ - Delete comment
    """

    permission_classes = [permissions.IsAuthenticated]

    # IAM organization field for CVAT's permission system
    iam_organization_field = 'task__organization'

    # Filter and search fields for CVAT compatibility
    search_fields = ('message', 'author__username')
    filter_fields = ['task', 'author', 'comment_type', 'parent_comment']
    simple_filters = ['task', 'author', 'comment_type']
    ordering_fields = ['created_date', 'updated_date', 'id']
    ordering = ['-created_date']

    # Lookup fields for filtering
    lookup_fields = {
        'author': 'author__username',
        'task': 'task__id',
    }

    def get_queryset(self):
        """Get comments with optimized queries."""
        queryset = TaskComment.objects.select_related(
            'author', 'task', 'parent_comment'
        ).prefetch_related(
            Prefetch(
                'replies',
                queryset=TaskComment.objects.select_related('author')[:10],
                to_attr='_prefetched_replies'
            )
        )

        # Filter by task if provided in URL
        task_id = self.kwargs.get('task_pk') or self.kwargs.get('task_id')
        if task_id:
            queryset = queryset.filter(task_id=task_id)

        return queryset.order_by('-created_date')

    def get_serializer_class(self):
        """Choose serializer based on action."""
        if self.action == 'create':
            return TaskCommentCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TaskCommentUpdateSerializer
        elif self.action == 'list':
            return TaskCommentSimpleSerializer
        else:
            return TaskCommentSerializer

    def create(self, request, *args, **kwargs):
        """Create a new comment."""
        # Get task from URL parameter
        task_id = kwargs.get('task_pk') or kwargs.get('task_id')
        if task_id:
            task = get_object_or_404(Task, id=task_id)
            # Add task to request data
            request.data['task'] = task.id

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()

        # Return full comment details
        response_serializer = TaskCommentSerializer(comment)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Update comment (author only)."""
        comment = self.get_object()

        # Check if user is the author
        if comment.author != request.user:
            return Response(
                {'error': 'You can only edit your own comments.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = self.get_serializer(comment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_comment = serializer.save()

        # Return full comment details
        response_serializer = TaskCommentSerializer(updated_comment)
        return Response(response_serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Delete comment (author only)."""
        comment = self.get_object()

        # Check if user is the author
        if comment.author != request.user:
            return Response(
                {'error': 'You can only delete your own comments.'},
                status=status.HTTP_403_FORBIDDEN
            )

        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def thread(self, request, pk=None):
        """Get full comment thread (parent + all replies)."""
        comment = self.get_object()
        thread_comments = comment.get_thread_comments()

        serializer = TaskCommentSimpleSerializer(thread_comments, many=True)
        return Response({
            'thread_id': comment.parent_comment_id or comment.id,
            'comments': serializer.data
        })

    @action(detail=False, methods=['get'])
    def by_type(self, request, task_pk=None):
        """Get comments filtered by type."""
        comment_type = request.query_params.get('type')
        if not comment_type:
            return Response(
                {'error': 'type parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset().filter(comment_type=comment_type)
        serializer = TaskCommentSimpleSerializer(queryset, many=True)
        return Response(serializer.data)


class TaskCommentsListView(viewsets.ReadOnlyModelViewSet):
    iam_supports_organization_params = True
    """
    Simplified view for listing task comments.

    Optimized for performance with minimal data.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TaskCommentSimpleSerializer

    # IAM organization field for CVAT's permission system
    iam_organization_field = 'task__organization'

    # Filter and search fields for CVAT compatibility
    search_fields = ('message', 'author__username')
    filter_fields = ['task', 'author', 'comment_type']
    ordering = ['-created_date']

    def get_queryset(self):
        """Get comments for a specific task."""
        task_id = self.kwargs.get('task_id') or self.kwargs.get('task_pk')
        if not task_id:
            return TaskComment.objects.none()

        return TaskComment.objects.filter(
            task_id=task_id
        ).select_related(
            'author', 'parent_comment'
        ).order_by('-created_date')

    def list(self, request, *args, **kwargs):
        """List comments with summary statistics."""
        queryset = self.get_queryset()

        # Get statistics
        total_comments = queryset.count()
        comment_types = queryset.values_list('comment_type', flat=True).distinct()

        # Paginate results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data['statistics'] = {
                'total_comments': total_comments,
                'comment_types': list(comment_types)
            }
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'statistics': {
                'total_comments': total_comments,
                'comment_types': list(comment_types)
            }
        })


# Standalone API Views for direct access

from rest_framework.views import APIView

class TaskCommentCreateView(APIView):
    """
    Standalone view for creating task comments.

    POST /api/custom/task-comments/create/
    """

    permission_classes = [permissions.IsAuthenticated]

    # IAM organization field for CVAT's permission system
    iam_organization_field = 'task__organization'

    def post(self, request):
        """Create a new task comment."""
        serializer = TaskCommentCreateSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            comment = serializer.save()
            response_serializer = TaskCommentSerializer(comment)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaskCommentsStatsView(APIView):
    """
    Get statistics about task comments.

    GET /api/custom/task-comments/stats/?task_id=1
    """

    permission_classes = [permissions.IsAuthenticated]

    # IAM organization field for CVAT's permission system
    iam_organization_field = 'task__organization'

    def get(self, request):
        """Get comment statistics for a task or all tasks."""
        task_id = request.query_params.get('task_id')

        queryset = TaskComment.objects.all()
        if task_id:
            queryset = queryset.filter(task_id=task_id)

        # Calculate statistics
        total_comments = queryset.count()

        # Comments by type
        type_stats = {}
        for choice in TaskComment.CommentType.choices:
            type_code, type_name = choice
            count = queryset.filter(comment_type=type_code).count()
            type_stats[type_code] = {
                'name': type_name,
                'count': count
            }

        # Recent activity (last 7 days)
        from datetime import datetime, timedelta
        week_ago = datetime.now() - timedelta(days=7)
        recent_comments = queryset.filter(created_date__gte=week_ago).count()

        # Top commenters
        from django.db.models import Count
        top_commenters = queryset.values(
            'author__username'
        ).annotate(
            comment_count=Count('id')
        ).order_by('-comment_count')[:5]

        return Response({
            'total_comments': total_comments,
            'comment_types': type_stats,
            'recent_activity': {
                'comments_last_week': recent_comments
            },
            'top_commenters': list(top_commenters),
            'task_id': task_id
        })
