# Copyright (C) 2025 CVAT Custom Module
# SPDX-License-Identifier: MIT

import io
import zipfile
from typing import Optional

from django.http import HttpResponse, Http404
from django.db.models import Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.models import Job, Task, Label, LabeledShape, LabeledImage, LabeledTrack, TrackedShape
from cvat.apps.engine.frame_provider import JobFrameProvider

from PIL import Image, ImageDraw, ImageFont
import os
import io
import zipfile
import json
from typing import Optional
from django.db import models
from django.utils import timezone
from django.db.models import Q


class DownloadAnnotatedFramesView(APIView):
    """
    API endpoint to download annotated frames for a specific job and optional label.

    Query Parameters:
    - job_id (required): ID of the job
    - label_id (optional): ID of the label to filter annotations

    Returns:
    - ZIP file containing annotated frames
    """

    permission_classes = [IsAuthenticated]

    def _get_font(self, size=24, bold=True):
        """Get a font for text rendering, with cross-platform compatibility."""

        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(current_dir, 'fonts')

        # Try to load our bundled fonts first
        if bold:
            font_path = os.path.join(fonts_dir, 'DejaVuSans-Bold.ttf')
        else:
            font_path = os.path.join(fonts_dir, 'DejaVuSans.ttf')

        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass

        # Fallback to system fonts (macOS/Linux)
        system_fonts = [
            "/System/Library/Fonts/Arial Bold.ttf",  # macOS
            "/System/Library/Fonts/Arial.ttf",       # macOS
            "/System/Library/Fonts/Helvetica.ttc",   # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",              # Arch Linux
            "/usr/share/fonts/TTF/DejaVuSans.ttf",                   # Arch Linux
        ]

        for font_path in system_fonts:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                continue

        # Final fallback to default font
        return ImageFont.load_default()

    def get(self, request):
        # Get query parameters
        job_id = request.query_params.get('job_id')
        label_id = request.query_params.get('label_id')

        if not job_id:
            return Response(
                {'error': 'job_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            job_id = int(job_id)
            if label_id:
                label_id = int(label_id)
        except ValueError:
            return Response(
                {'error': 'job_id and label_id must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the job
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            raise Http404("Job not found")

        # Basic permission check - user must be authenticated
        # TODO: Add more granular permission checking based on job assignee/organization
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get the label if specified
        label = None
        if label_id:
            try:
                label = Label.objects.get(id=label_id)
            except Label.DoesNotExist:
                return Response(
                    {'error': 'Label not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Get annotated frames
        annotated_frames = self._get_annotated_frames(job, label)

        if not annotated_frames:
            return Response(
                {'message': 'No annotated frames found for the specified criteria'},
                status=status.HTTP_200_OK
            )

        # Create ZIP file
        zip_buffer = self._create_annotated_frames_zip(job, annotated_frames, label)

        # Prepare response
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        filename = f"job_{job_id}_annotated_frames"
        if label:
            filename += f"_label_{label.name}"
        filename += ".zip"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _get_annotated_frames(self, job: Job, label: Optional[Label] = None) -> set:
        """Get all frame numbers that have annotations for the given job and optional label."""

        # Build query filter
        query_filter = Q(job=job)
        if label:
            query_filter &= Q(label=label)

        # Get frames from different annotation types
        annotated_frames = set()

        # Get frames from LabeledShape (rectangles, polygons, etc.)
        shape_frames = LabeledShape.objects.filter(query_filter).values_list('frame', flat=True)
        annotated_frames.update(shape_frames)

        # Get frames from LabeledImage (tags)
        image_frames = LabeledImage.objects.filter(query_filter).values_list('frame', flat=True)
        annotated_frames.update(image_frames)

        # Get frames from TrackedShape (tracks)
        track_query = Q(track__job=job)
        if label:
            track_query &= Q(track__label=label)
        tracked_frames = TrackedShape.objects.filter(track_query).values_list('frame', flat=True)
        annotated_frames.update(tracked_frames)

        return annotated_frames

    def _create_annotated_frames_zip(self, job: Job, frame_numbers: set, label: Optional[Label] = None) -> io.BytesIO:
        """Create a ZIP file containing annotated frames."""

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Get frame provider for the job
            frame_provider = JobFrameProvider(job)

            for frame_number in sorted(frame_numbers):
                try:
                    # Get the original frame
                    frame_data = frame_provider.get_frame(frame_number)

                    # Convert to PIL Image
                    image = Image.open(io.BytesIO(frame_data.data.getvalue()))

                    # Draw annotations on the frame
                    annotated_image = self._draw_annotations_on_frame(image, job, frame_number, label)

                    # Save to ZIP
                    img_buffer = io.BytesIO()
                    annotated_image.save(img_buffer, format='PNG')

                    filename = f"frame_{frame_number:06d}.png"
                    zip_file.writestr(filename, img_buffer.getvalue())

                except Exception as e:
                    # Log error but continue with other frames
                    print(f"Error processing frame {frame_number}: {str(e)}")
                    continue

        zip_buffer.seek(0)
        return zip_buffer

    def _draw_annotations_on_frame(self, image: Image.Image, job: Job, frame_number: int, label: Optional[Label] = None) -> Image.Image:
        """Draw annotations on the given frame."""

        # Create a copy of the image to draw on
        annotated_image = image.copy()
        draw = ImageDraw.Draw(annotated_image)

        # Build query filter
        query_filter = Q(job=job, frame=frame_number)
        if label:
            query_filter &= Q(label=label)

        # Draw LabeledShapes (rectangles, polygons, etc.)
        shapes = LabeledShape.objects.filter(query_filter)
        for shape in shapes:
            self._draw_shape(draw, shape)

        # Draw TrackedShapes
        track_query = Q(track__job=job, frame=frame_number)
        if label:
            track_query &= Q(track__label=label)
        tracked_shapes = TrackedShape.objects.filter(track_query)
        for tracked_shape in tracked_shapes:
            self._draw_tracked_shape(draw, tracked_shape)

        # Note: LabeledImage (tags) don't have visual representation on frames

        return annotated_image

    def _draw_shape(self, draw: ImageDraw.Draw, shape: LabeledShape):
        """Draw a single shape annotation with label text."""

        color = shape.label.color if shape.label.color else "#FF0000"
        points = shape.points
        label_name = shape.label.name

        # Load cross-platform font
        font = self._get_font(size=24, bold=True)

        text_position = None

        if shape.type == 'rectangle' and len(points) >= 4:
            # Rectangle: [x1, y1, x2, y2]
            x1, y1, x2, y2 = points[:4]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            text_position = (x1, y1 - 35)  # Above the rectangle (more space for larger text)

        elif shape.type == 'polygon' and len(points) >= 6:
            # Polygon: [x1, y1, x2, y2, ..., xn, yn]
            polygon_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            draw.polygon(polygon_points, outline=color, width=2)
            # Use first point for text position
            text_position = (polygon_points[0][0], polygon_points[0][1] - 35)

        elif shape.type == 'polyline' and len(points) >= 4:
            # Polyline: [x1, y1, x2, y2, ..., xn, yn]
            line_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            for i in range(len(line_points) - 1):
                draw.line([line_points[i], line_points[i+1]], fill=color, width=2)
            # Use first point for text position
            text_position = (line_points[0][0], line_points[0][1] - 35)

        elif shape.type == 'points':
            # Points: [x1, y1, x2, y2, ..., xn, yn]
            for i in range(0, len(points), 2):
                if i + 1 < len(points):
                    x, y = points[i], points[i+1]
                    # Draw small circle for each point
                    radius = 3
                    draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=color)
                    if i == 0:  # Use first point for text
                        text_position = (x, y - 35)

        elif shape.type == 'ellipse' and len(points) >= 4:
            # Ellipse: [cx, cy, rx, ry]
            cx, cy, rx, ry = points[:4]
            draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], outline=color, width=2)
            text_position = (cx - rx, cy - ry - 35)  # Above the ellipse (more space for larger text)

        # Draw label text if we have a position
        if text_position and label_name:
            # Add padding around text for better visibility
            padding = 8
            text_bbox = draw.textbbox(text_position, label_name, font=font)
            # Expand bbox with padding
            padded_bbox = (
                text_bbox[0] - padding,
                text_bbox[1] - padding,
                text_bbox[2] + padding,
                text_bbox[3] + padding
            )

            # Draw black background with white border for maximum contrast
            draw.rectangle(padded_bbox, fill="black", outline="white", width=2)

            # Draw text in bright yellow for maximum visibility
            draw.text(text_position, label_name, fill="yellow", font=font)

    def _draw_tracked_shape(self, draw: ImageDraw.Draw, tracked_shape: TrackedShape):
        """Draw a tracked shape annotation with label text."""

        color = tracked_shape.track.label.color if tracked_shape.track.label.color else "#00FF00"
        points = tracked_shape.points
        label_name = tracked_shape.track.label.name

        # Load cross-platform font
        font = self._get_font(size=24, bold=True)

        text_position = None

        # Use the same drawing logic as regular shapes
        if tracked_shape.type == 'rectangle' and len(points) >= 4:
            x1, y1, x2, y2 = points[:4]
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            text_position = (x1, y1 - 35)  # Above the rectangle (more space for larger text)

        elif tracked_shape.type == 'polygon' and len(points) >= 6:
            polygon_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            draw.polygon(polygon_points, outline=color, width=2)
            text_position = (polygon_points[0][0], polygon_points[0][1] - 35)

        # Draw label text if we have a position
        if text_position and label_name:
            # Add padding around text for better visibility
            padding = 8
            text_bbox = draw.textbbox(text_position, label_name, font=font)
            # Expand bbox with padding
            padded_bbox = (
                text_bbox[0] - padding,
                text_bbox[1] - padding,
                text_bbox[2] + padding,
                text_bbox[3] + padding
            )

            # Draw black background with white border for maximum contrast
            draw.rectangle(padded_bbox, fill="black", outline="white", width=2)

            # Draw text in bright yellow for maximum visibility
            draw.text(text_position, label_name, fill="yellow", font=font)

        # Add more shape types as needed...


class DownloadTaskFramesView(APIView):
    """
    Production-grade API endpoint to download annotated frames for an entire task.

    Query Parameters:
    - task_id (required): ID of the task
    - label_id (optional): ID of the label to filter annotations

    Returns:
    - ZIP file containing all annotated frames from all jobs in the task
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get query parameters
        task_id = request.query_params.get('task_id')
        label_id = request.query_params.get('label_id')

        if not task_id:
            return Response(
                {'error': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            task_id = int(task_id)
            if label_id:
                label_id = int(label_id)
        except ValueError:
            return Response(
                {'error': 'task_id and label_id must be integers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the task
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Basic permission check - user must be authenticated
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get the label if specified
        label = None
        if label_id:
            try:
                # Check if label belongs to task or its project
                label = Label.objects.filter(
                    models.Q(task=task) | models.Q(project=task.project)
                ).get(id=label_id)
            except Label.DoesNotExist:
                return Response(
                    {'error': 'Label not found or not associated with this task'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Get all jobs in the task
        jobs = Job.objects.filter(segment__task=task)
        if not jobs.exists():
            return Response(
                {'message': 'No jobs found in this task'},
                status=status.HTTP_200_OK
            )

        # Get annotated frames from all jobs
        all_annotated_frames = {}  # {job_id: set_of_frame_numbers}
        total_frames = 0

        for job in jobs:
            job_frames = self._get_annotated_frames(job, label)
            if job_frames:
                all_annotated_frames[job.id] = job_frames
                total_frames += len(job_frames)

        if total_frames == 0:
            return Response(
                {'message': 'No annotated frames found for the specified criteria'},
                status=status.HTTP_200_OK
            )

        # Create ZIP file with all annotated frames
        zip_buffer = self._create_task_frames_zip(task, all_annotated_frames, label)

        # Prepare response
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        filename = f"task_{task_id}_annotated_frames"
        if label:
            filename += f"_label_{label.name}"
        filename += ".zip"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def _get_annotated_frames(self, job: Job, label: Optional[Label] = None) -> set:
        """Get all frame numbers that have annotations for the given job and optional label."""

        # Build query filter
        query_filter = Q(job=job)
        if label:
            query_filter &= Q(label=label)

        # Get frames from different annotation types
        annotated_frames = set()

        # Get frames from LabeledShape (rectangles, polygons, etc.)
        shape_frames = LabeledShape.objects.filter(query_filter).values_list('frame', flat=True)
        annotated_frames.update(shape_frames)

        # Get frames from LabeledImage (tags)
        image_frames = LabeledImage.objects.filter(query_filter).values_list('frame', flat=True)
        annotated_frames.update(image_frames)

        # Get frames from TrackedShape (tracks)
        track_query = Q(track__job=job)
        if label:
            track_query &= Q(track__label=label)
        tracked_frames = TrackedShape.objects.filter(track_query).values_list('frame', flat=True)
        annotated_frames.update(tracked_frames)

        return annotated_frames

    def _create_task_frames_zip(self, task: Task, job_frames_dict: dict, label: Optional[Label] = None) -> io.BytesIO:
        """Create a ZIP file containing annotated frames from all jobs in the task."""

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:

            # Add metadata file
            metadata = {
                "task_id": task.id,
                "task_name": task.name,
                "label_filter": label.name if label else "all_labels",
                "total_jobs": len(job_frames_dict),
                "total_frames": sum(len(frames) for frames in job_frames_dict.values()),
                "generated_at": timezone.now().isoformat(),
                "cvat_version": "custom_export_v1.0"
            }

            zip_file.writestr("metadata.json", json.dumps(metadata, indent=2))

            # Process each job
            for job_id, frame_numbers in job_frames_dict.items():
                job = Job.objects.get(id=job_id)
                job_folder = f"job_{job_id}/"

                # Get frame provider for the job
                frame_provider = JobFrameProvider(job)

                for frame_number in sorted(frame_numbers):
                    try:
                        # Get the original frame
                        frame_data = frame_provider.get_frame(frame_number)

                        # Convert to PIL Image
                        image = Image.open(io.BytesIO(frame_data.data.getvalue()))

                        # Apply production-grade annotation overlay
                        annotated_image = self._create_production_overlay(image, job, frame_number, label)

                        # Save to ZIP with high quality
                        img_buffer = io.BytesIO()
                        annotated_image.save(img_buffer, format='PNG', optimize=True, compress_level=6)

                        filename = f"{job_folder}frame_{frame_number:06d}.png"
                        zip_file.writestr(filename, img_buffer.getvalue())

                    except Exception as e:
                        # Log error but continue with other frames
                        print(f"Error processing job {job_id} frame {frame_number}: {str(e)}")
                        continue

        zip_buffer.seek(0)
        return zip_buffer

    def _create_production_overlay(self, image: Image.Image, job: Job, frame_number: int, label: Optional[Label] = None) -> Image.Image:
        """Create production-grade annotation overlay with enhanced visual quality."""

        # Create a copy with higher quality processing
        annotated_image = image.copy()

        # Use high-quality drawing with anti-aliasing
        draw = ImageDraw.Draw(annotated_image)

        # Load production-grade font
        font_large = self._get_font(size=28, bold=True)  # Larger for better visibility
        font_small = self._get_font(size=16, bold=False)  # For additional info

        # Build query filter
        query_filter = Q(job=job, frame=frame_number)
        if label:
            query_filter &= Q(label=label)

        # Draw LabeledShapes with enhanced styling
        shapes = LabeledShape.objects.filter(query_filter).select_related('label')
        for shape in shapes:
            self._draw_production_shape(draw, shape, font_large, font_small)

        # Draw TrackedShapes with enhanced styling
        track_query = Q(track__job=job, frame=frame_number)
        if label:
            track_query &= Q(track__label=label)
        tracked_shapes = TrackedShape.objects.filter(track_query).select_related('track__label')
        for tracked_shape in tracked_shapes:
            self._draw_production_tracked_shape(draw, tracked_shape, font_large, font_small)

        # Add frame information overlay
        self._add_frame_info_overlay(draw, job, frame_number, font_small)

        return annotated_image

    def _draw_production_shape(self, draw: ImageDraw.Draw, shape: LabeledShape, font_large, font_small):
        """Draw shape with production-grade styling."""

        # Enhanced color handling
        color = shape.label.color if shape.label.color else "#FF0000"
        # Convert hex to RGB for better processing
        if color.startswith('#'):
            color_rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        else:
            color_rgb = (255, 0, 0)  # Default red

        points = shape.points
        label_name = shape.label.name

        # Enhanced shape drawing with anti-aliasing effect (multiple thin lines)
        line_width = 3

        text_position = None

        if shape.type == 'rectangle' and len(points) >= 4:
            x1, y1, x2, y2 = points[:4]
            # Draw multiple thin lines for anti-aliasing effect
            for i in range(line_width):
                draw.rectangle([x1-i, y1-i, x2+i, y2+i], outline=color, width=1)
            text_position = (x1, y1 - 45)

        elif shape.type == 'polygon' and len(points) >= 6:
            polygon_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            for i in range(line_width):
                # Offset polygon for thickness
                offset_points = [(x+i, y+i) for x, y in polygon_points]
                draw.polygon(offset_points, outline=color, width=1)
            text_position = (polygon_points[0][0], polygon_points[0][1] - 45)

        elif shape.type == 'polyline' and len(points) >= 4:
            line_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            for i in range(len(line_points) - 1):
                for j in range(line_width):
                    draw.line([
                        (line_points[i][0]+j, line_points[i][1]+j),
                        (line_points[i+1][0]+j, line_points[i+1][1]+j)
                    ], fill=color, width=1)
            text_position = (line_points[0][0], line_points[0][1] - 45)

        elif shape.type == 'points':
            for i in range(0, len(points), 2):
                if i + 1 < len(points):
                    x, y = points[i], points[i+1]
                    # Enhanced point visualization
                    radius = 6
                    draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=color, outline="white", width=2)
                    if i == 0:
                        text_position = (x, y - 45)

        elif shape.type == 'ellipse' and len(points) >= 4:
            cx, cy, rx, ry = points[:4]
            for i in range(line_width):
                draw.ellipse([cx-rx-i, cy-ry-i, cx+rx+i, cy+ry+i], outline=color, width=1)
            text_position = (cx - rx, cy - ry - 45)

        # Enhanced text rendering with production styling
        if text_position and label_name:
            self._draw_production_text(draw, text_position, label_name, color_rgb, font_large, font_small)

    def _draw_production_tracked_shape(self, draw: ImageDraw.Draw, tracked_shape: TrackedShape, font_large, font_small):
        """Draw tracked shape with production-grade styling and track info."""

        color = tracked_shape.track.label.color if tracked_shape.track.label.color else "#00FF00"
        if color.startswith('#'):
            color_rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        else:
            color_rgb = (0, 255, 0)

        points = tracked_shape.points
        label_name = f"{tracked_shape.track.label.name} (Track #{tracked_shape.track.id})"

        line_width = 3
        text_position = None

        if tracked_shape.type == 'rectangle' and len(points) >= 4:
            x1, y1, x2, y2 = points[:4]
            # Enhanced rectangle with track styling
            for i in range(line_width):
                draw.rectangle([x1-i, y1-i, x2+i, y2+i], outline=color, width=1)
            # Add track indicator (small dot)
            draw.ellipse([x2-8, y1-8, x2+8, y1+8], fill=color, outline="white", width=2)
            text_position = (x1, y1 - 45)

        elif tracked_shape.type == 'polygon' and len(points) >= 6:
            polygon_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            for i in range(line_width):
                offset_points = [(x+i, y+i) for x, y in polygon_points]
                draw.polygon(offset_points, outline=color, width=1)
            text_position = (polygon_points[0][0], polygon_points[0][1] - 45)

        # Enhanced text rendering for tracks
        if text_position and label_name:
            self._draw_production_text(draw, text_position, label_name, color_rgb, font_large, font_small)

    def _draw_production_text(self, draw: ImageDraw.Draw, position, text, color_rgb, font_large, font_small):
        """Draw text with production-grade styling and effects."""

        x, y = position

        # Enhanced text background with gradient effect
        padding = 12
        text_bbox = draw.textbbox(position, text, font=font_large)

        # Create enhanced background
        bg_bbox = (
            text_bbox[0] - padding,
            text_bbox[1] - padding,
            text_bbox[2] + padding,
            text_bbox[3] + padding
        )

        # Multi-layer background for depth
        # Shadow layer
        shadow_bbox = (bg_bbox[0]+2, bg_bbox[1]+2, bg_bbox[2]+2, bg_bbox[3]+2)
        draw.rectangle(shadow_bbox, fill=(0, 0, 0, 128))  # Semi-transparent shadow

        # Main background
        draw.rectangle(bg_bbox, fill="black", outline="white", width=3)

        # Inner border for premium look
        inner_bbox = (bg_bbox[0]+2, bg_bbox[1]+2, bg_bbox[2]-2, bg_bbox[3]-2)
        draw.rectangle(inner_bbox, outline=color_rgb, width=1)

        # Main text with enhanced visibility
        draw.text(position, text, fill="yellow", font=font_large)

        # Add subtle outline to text for extra clarity
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1)]:
            draw.text((position[0]+dx, position[1]+dy), text, fill="black", font=font_large)
        draw.text(position, text, fill="yellow", font=font_large)

    def _add_frame_info_overlay(self, draw: ImageDraw.Draw, job: Job, frame_number: int, font_small):
        """Add frame information overlay for production use."""

        # Get image dimensions
        img_width = draw.im.size[0]
        img_height = draw.im.size[1]

        # Frame info text
        info_text = f"Task: {job.segment.task.name} | Job: {job.id} | Frame: {frame_number}"

        # Position at bottom right
        text_bbox = draw.textbbox((0, 0), info_text, font=font_small)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        position = (img_width - text_width - 20, img_height - text_height - 20)

        # Semi-transparent background
        bg_bbox = (
            position[0] - 8,
            position[1] - 4,
            position[0] + text_width + 8,
            position[1] + text_height + 4
        )

        draw.rectangle(bg_bbox, fill=(0, 0, 0, 180), outline="gray", width=1)
        draw.text(position, info_text, fill="white", font=font_small)

    def _get_font(self, size=24, bold=True):
        """Get a font for text rendering, with cross-platform compatibility."""

        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(current_dir, 'fonts')

        # Try to load our bundled fonts first
        if bold:
            font_path = os.path.join(fonts_dir, 'DejaVuSans-Bold.ttf')
        else:
            font_path = os.path.join(fonts_dir, 'DejaVuSans.ttf')

        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception:
            pass

        # Fallback to system fonts (macOS/Linux)
        system_fonts = [
            "/System/Library/Fonts/Arial Bold.ttf",  # macOS
            "/System/Library/Fonts/Arial.ttf",       # macOS
            "/System/Library/Fonts/Helvetica.ttc",   # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",              # Arch Linux
            "/usr/share/fonts/TTF/DejaVuSans.ttf",                   # Arch Linux
        ]

        for font_path in system_fonts:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                continue

        # Final fallback to default font
        return ImageFont.load_default()
