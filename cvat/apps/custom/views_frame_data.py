# Copyright (C) 2025 CVAT Custom Frame Data Module
# SPDX-License-Identifier: MIT

"""
High-performance per-frame API for retrieving frame metadata and annotations.

Provides industry-standard, optimized endpoint for frame-by-frame UI navigation.
"""

from django.http import Http404
from django.db.models import Q, Prefetch
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.models import Job, LabeledShape, LabeledImage, TrackedShape, LabeledTrack
from cvat.apps.engine.serializers import LabeledShapeSerializer, LabeledImageSerializer


class JobFrameView(APIView):
    """
    Industry-standard per-frame API for retrieving frame metadata and annotations.

    GET /api/custom/jobs/{job_id}/frame/{frame_number}/?org=

    Returns:
    - Frame metadata (width, height, name)
    - All annotations for the specific frame (shapes, tracks, tags)
    - Annotation counts and summary

    Optimized for:
    - Single database query with prefetch_related
    - Minimal data transfer
    - Frame-by-frame UI navigation
    - High performance
    """

    permission_classes = [IsAuthenticated]

    # IAM organization field for CVAT's permission system
    iam_organization_field = 'segment__task__organization'

    def get(self, request, job_id: int, frame_number: int):
        """
        Get frame metadata and annotations for a specific frame.

        Args:
            job_id: Job identifier
            frame_number: Frame number within the job

        Returns:
            JSON response with frame meta and annotations
        """
        try:
            # Get job with optimized query - single DB hit
            job = self._get_job_optimized(job_id)

            # Validate frame number is within job range
            self._validate_frame_number(job, frame_number)

            # Get frame metadata
            frame_meta = self._get_frame_metadata(job, frame_number)

            # Get all annotations for this frame - optimized bulk query
            annotations = self._get_frame_annotations(job, frame_number)

            # Build response
            response_data = {
                "job_id": job.id,
                "frame_number": frame_number,
                "frame_meta": frame_meta,
                "annotations": annotations,
                "has_annotations": self._has_annotations(annotations),
                "annotation_count": self._count_annotations(annotations)
            }

            return Response(response_data)

        except Job.DoesNotExist:
            raise Http404("Job not found")
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': 'Internal server error',
                    'details': str(e) if request.user.is_staff else None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_job_optimized(self, job_id: int) -> Job:
        """Get job with optimized query including related data."""
        return Job.objects.select_related(
            'segment',
            'segment__task',
            'segment__task__data',
            'segment__task__data__video'
        ).prefetch_related(
            Prefetch(
                'segment__task__data__images',
                to_attr='_prefetched_images'
            )
        ).get(id=job_id)

    def _validate_frame_number(self, job: Job, frame_number: int):
        """Validate frame number is within job's frame range."""
        if not (job.segment.start_frame <= frame_number <= job.segment.stop_frame):
            raise ValueError(
                f"Frame {frame_number} is outside job range "
                f"[{job.segment.start_frame}, {job.segment.stop_frame}]"
            )

    def _get_frame_metadata(self, job: Job, frame_number: int) -> dict:
        """Get metadata for a specific frame."""
        db_data = job.segment.task.data

        # Calculate frame index within the data
        frame_step = db_data.get_frame_step()
        data_frame_number = db_data.start_frame + frame_number * frame_step

        # Get frame metadata
        if hasattr(db_data, 'video') and db_data.video:
            # Video data
            return {
                "width": db_data.video.width,
                "height": db_data.video.height,
                "name": f"frame_{frame_number:06d}",
                "related_files": 0
            }
        else:
            # Image data - find the specific image
            images = getattr(db_data, '_prefetched_images', None)
            if not images:
                images = list(db_data.images.filter(frame=data_frame_number))

            # Find image for this frame
            frame_image = next(
                (img for img in images if img.frame == data_frame_number),
                None
            )

            if frame_image:
                return {
                    "width": frame_image.width,
                    "height": frame_image.height,
                    "name": frame_image.path,
                    "related_files": frame_image.related_files.count() if hasattr(frame_image, 'related_files') else 0
                }
            else:
                # Fallback for missing frame data
                return {
                    "width": 0,
                    "height": 0,
                    "name": f"frame_{frame_number:06d}",
                    "related_files": 0
                }

    def _get_frame_annotations(self, job: Job, frame_number: int) -> dict:
        """Get all annotations for a specific frame with optimized queries."""

        # Single optimized query for shapes
        shapes = LabeledShape.objects.filter(
            job=job,
            frame=frame_number
        ).select_related('label').prefetch_related('attributes')

        # Single optimized query for tags
        tags = LabeledImage.objects.filter(
            job=job,
            frame=frame_number
        ).select_related('label').prefetch_related('attributes')

        # Single optimized query for tracked shapes
        tracked_shapes = TrackedShape.objects.filter(
            track__job=job,
            frame=frame_number
        ).select_related('track', 'track__label').prefetch_related('track__attributes')

        # Serialize data efficiently
        return {
            "shapes": self._serialize_shapes(shapes),
            "tags": self._serialize_tags(tags),
            "tracks": self._serialize_tracked_shapes(tracked_shapes)
        }

    def _serialize_shapes(self, shapes) -> list:
        """Serialize shapes with minimal data transfer."""
        return [
            {
                "id": shape.id,
                "label": shape.label.name,
                "label_id": shape.label.id,
                "type": shape.type,
                "points": shape.points,
                "occluded": shape.occluded,
                "z_order": shape.z_order,
                "attributes": [
                    {
                        "spec_id": attr.spec.id,
                        "name": attr.spec.name,
                        "value": attr.value
                    }
                    for attr in shape.attributes.all()
                ]
            }
            for shape in shapes
        ]

    def _serialize_tags(self, tags) -> list:
        """Serialize tags with minimal data transfer."""
        return [
            {
                "id": tag.id,
                "label": tag.label.name,
                "label_id": tag.label.id,
                "attributes": [
                    {
                        "spec_id": attr.spec.id,
                        "name": attr.spec.name,
                        "value": attr.value
                    }
                    for attr in tag.attributes.all()
                ]
            }
            for tag in tags
        ]

    def _serialize_tracked_shapes(self, tracked_shapes) -> list:
        """Serialize tracked shapes with minimal data transfer."""
        # Group by track to avoid duplicates
        tracks_data = {}

        for tracked_shape in tracked_shapes:
            track_id = tracked_shape.track.id

            if track_id not in tracks_data:
                tracks_data[track_id] = {
                    "track_id": track_id,
                    "label": tracked_shape.track.label.name,
                    "label_id": tracked_shape.track.label.id,
                    "attributes": [
                        {
                            "spec_id": attr.spec.id,
                            "name": attr.spec.name,
                            "value": attr.value
                        }
                        for attr in tracked_shape.track.attributes.all()
                    ],
                    "shape": {
                        "id": tracked_shape.id,
                        "type": tracked_shape.type,
                        "points": tracked_shape.points,
                        "occluded": tracked_shape.occluded,
                        "outside": tracked_shape.outside,
                        "z_order": tracked_shape.z_order
                    }
                }

        return list(tracks_data.values())

    def _has_annotations(self, annotations: dict) -> bool:
        """Check if frame has any annotations."""
        return (
            len(annotations["shapes"]) > 0 or
            len(annotations["tags"]) > 0 or
            len(annotations["tracks"]) > 0
        )

    def _count_annotations(self, annotations: dict) -> int:
        """Count total annotations for the frame."""
        return (
            len(annotations["shapes"]) +
            len(annotations["tags"]) +
            len(annotations["tracks"])
        )
