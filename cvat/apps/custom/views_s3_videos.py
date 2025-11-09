# Copyright (C) 2025 CVAT Custom S3 Videos Module
# SPDX-License-Identifier: MIT

"""
S3 Video Presigned URL APIs

Provides endpoints to list videos from S3 and generate presigned URLs for streaming.
"""

import os
from django.http import Http404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.models import Task
from .models import TaskTrainMetadata
from .s3_utils import create_s3_generator_from_env
from drf_spectacular.utils import extend_schema


class TaskVideosView(APIView):
    """
    Get all videos from task's S3 path with presigned URLs for streaming.

    GET /api/custom/tasks/{task_id}/videos/

    Query Parameters:
    - expiration: URL expiration time in seconds (default: 3600 = 1 hour)

    Returns:
    - List of videos with presigned URLs
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='custom_list_task_videos', summary='List all videos for a task')
    def get(self, request, task_id):
        """
        Get videos from task's server_files_path with presigned URLs.

        Args:
            task_id: Task ID

        Returns:
            JSON response with video list and presigned URLs
        """
        # Get expiration from query params (default 1 hour)
        expiration = int(request.query_params.get('expiration', 3600))

        # Validate expiration (between 1 minute and 7 days)
        if expiration < 60:
            return Response(
                {'error': 'Expiration must be at least 60 seconds'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if expiration > 604800:  # 7 days
            return Response(
                {'error': 'Expiration cannot exceed 604800 seconds (7 days)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Get task
            task = Task.objects.select_related('data').get(pk=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get train metadata with server_files_path
        try:
            train_metadata = task.train_metadata
            server_files_path = train_metadata.server_files_path
        except TaskTrainMetadata.DoesNotExist:
            return Response(
                {
                    'error': 'Task does not have train metadata',
                    'task_id': task_id,
                    'videos': []
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if server_files_path is valid
        if not server_files_path or server_files_path == '/':
            return Response(
                {
                    'message': 'Task does not have a valid server_files_path',
                    'task_id': task_id,
                    'task_name': task.name,
                    'server_files_path': server_files_path,
                    'videos': []
                },
                status=status.HTTP_200_OK
            )

        # Generate presigned URLs for videos using environment variables
        try:
            s3_generator, bucket_name = create_s3_generator_from_env()

            # List videos and get presigned URLs
            videos = s3_generator.get_all_videos_with_urls(
                bucket_name=bucket_name,
                folder_path=server_files_path,
                expiration=expiration
            )

            return Response({
                'task_id': task_id,
                'task_name': task.name,
                'server_files_path': server_files_path,
                's3_bucket': bucket_name,
                's3_region': os.getenv('CVAT_S3_REGION', 'us-east-1'),
                'video_count': len(videos),
                'expiration_seconds': expiration,
                'videos': videos,
                'note': 'S3 configured from environment variables'
            })

        except PermissionError as e:
            return Response(
                {
                    'error': f'Access denied to S3 bucket: {str(e)}',
                    'task_id': task_id,
                    'videos': []
                },
                status=status.HTTP_403_FORBIDDEN
            )
        except ValueError as e:
            # Missing environment variables
            return Response(
                {
                    'error': 'S3 not configured',
                    'detail': str(e),
                    'hint': 'Set CVAT_S3_ACCESS_KEY_ID, CVAT_S3_SECRET_ACCESS_KEY, and CVAT_S3_BUCKET_NAME environment variables',
                    'task_id': task_id,
                    'videos': []
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response(
                {
                    'error': f'Failed to get videos: {str(e)}',
                    'task_id': task_id,
                    'videos': []
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TaskSingleVideoView(APIView):
    """
    Get presigned URL for a specific video in task's S3 path.

    GET /api/custom/tasks/{task_id}/videos/{video_path}/

    Query Parameters:
    - expiration: URL expiration time in seconds (default: 3600)
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='custom_get_single_video', summary='Get presigned URL for a specific video')
    def get(self, request, task_id, video_path):
        """
        Get presigned URL for a specific video.

        Args:
            task_id: Task ID
            video_path: Relative path to video within server_files_path

        Returns:
            JSON response with presigned URL
        """
        # Get expiration from query params
        expiration = int(request.query_params.get('expiration', 3600))

        try:
            # Get task
            task = Task.objects.select_related('data').get(pk=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get train metadata
        try:
            train_metadata = task.train_metadata
            server_files_path = train_metadata.server_files_path
        except TaskTrainMetadata.DoesNotExist:
            return Response(
                {'error': 'Task does not have train metadata'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if server_files_path is valid
        if not server_files_path or server_files_path == '/':
            return Response(
                {'error': 'Task does not have a valid server_files_path'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Construct full video path
        if server_files_path.endswith('/'):
            full_video_path = f"{server_files_path}{video_path}"
        else:
            full_video_path = f"{server_files_path}/{video_path}"

        # Generate presigned URL using environment variables
        try:
            s3_generator, bucket_name = create_s3_generator_from_env()

            video_info = s3_generator.get_video_presigned_url(
                bucket_name=bucket_name,
                video_path=full_video_path,
                expiration=expiration
            )

            return Response({
                'task_id': task_id,
                'task_name': task.name,
                'server_files_path': server_files_path,
                'video': video_info,
                'note': 'S3 configured from environment variables'
            })

        except FileNotFoundError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            # Missing environment variables
            return Response(
                {
                    'error': 'S3 not configured',
                    'detail': str(e),
                    'hint': 'Set CVAT_S3_ACCESS_KEY_ID, CVAT_S3_SECRET_ACCESS_KEY, and CVAT_S3_BUCKET_NAME environment variables'
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to get video: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TaskVideosQuickView(APIView):
    """
    Quick endpoint to check if task has videos available.

    GET /api/custom/tasks/{task_id}/videos/check/

    Returns basic info without generating presigned URLs.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='custom_check_videos_availability', summary='Check if videos are available for a task')
    def get(self, request, task_id):
        """
        Check if task has videos available.

        Args:
            task_id: Task ID

        Returns:
            JSON response with video availability info
        """
        try:
            task = Task.objects.select_related('data').get(pk=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Get train metadata
        try:
            train_metadata = task.train_metadata
            server_files_path = train_metadata.server_files_path
        except TaskTrainMetadata.DoesNotExist:
            return Response({
                'task_id': task_id,
                'has_server_files_path': False,
                'has_s3_configured': False,
                'can_list_videos': False
            })

        # Check validity
        has_valid_path = bool(server_files_path and server_files_path != '/')

        # Check if S3 is configured via environment variables
        has_s3_config = all([
            os.getenv('CVAT_S3_ACCESS_KEY_ID'),
            os.getenv('CVAT_S3_SECRET_ACCESS_KEY'),
            os.getenv('CVAT_S3_BUCKET_NAME')
        ])

        return Response({
            'task_id': task_id,
            'task_name': task.name,
            'has_server_files_path': has_valid_path,
            'server_files_path': server_files_path if has_valid_path else None,
            'has_s3_configured': has_s3_config,
            's3_bucket': os.getenv('CVAT_S3_BUCKET_NAME') if has_s3_config else None,
            'can_list_videos': has_valid_path and has_s3_config,
            'video_endpoint': f'/api/custom/tasks/{task_id}/videos/' if has_valid_path and has_s3_config else None,
            'note': 'S3 credentials are configured globally via environment variables'
        })

