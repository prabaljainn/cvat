# Copyright (C) 2025 CVAT Custom Export Module
# SPDX-License-Identifier: MIT

"""
CVAT-Integrated Export Views that leverage CVAT's built-in export infrastructure
while adding custom label filtering and annotation overlay functionality.
"""

import io
import json
import tempfile
from typing import Optional

from django.http import HttpResponse, Http404
from django.db import transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from cvat.apps.engine.models import Task, Label
from cvat.apps.dataset_manager.task import TaskAnnotation
from cvat.apps.dataset_manager.bindings import TaskData
from cvat.apps.engine.frame_provider import TaskFrameProvider

from PIL import Image, ImageDraw, ImageFont
import os
import zipfile
from django.db.models import Q


class CVATIntegratedExportView(APIView):
    """
    CVAT-integrated export endpoint that leverages CVAT's export infrastructure
    while adding custom label filtering and annotation overlay functionality.

    This approach:
    1. Uses CVAT's TaskAnnotation and export system
    2. Adds custom label filtering
    3. Provides annotated image overlays
    4. Maintains compatibility with CVAT's architecture
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get query parameters
        task_id = request.query_params.get('task_id')
        label_id = request.query_params.get('label_id')
        export_format = request.query_params.get('format', 'annotated_images')

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

        # Get the task using CVAT's system
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            raise Http404("Task not found")

        # Permission check
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get the label if specified
        label = None
        if label_id:
            try:
                label = Label.objects.filter(
                    Q(task=task) | Q(project=task.project)
                ).get(id=label_id)
            except Label.DoesNotExist:
                return Response(
                    {'error': 'Label not found or not associated with this task'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Create export using CVAT's infrastructure
        if export_format == 'annotated_images':
            zip_buffer = self._create_annotated_images_export(task, label)
        else:
            # Fallback to standard CVAT export
            zip_buffer = self._create_standard_cvat_export(task, export_format)

        # Prepare response
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        filename = f"task_{task_id}_export"
        if label:
            filename += f"_label_{label.name}"
        if export_format == 'annotated_images':
            filename += "_annotated"
        filename += ".zip"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @transaction.atomic
    def _create_annotated_images_export(self, task: Task, label: Optional[Label] = None) -> io.BytesIO:
        """Create annotated images export using CVAT's TaskAnnotation system."""

        try:
            # Use CVAT's TaskAnnotation system
            task_annotation = TaskAnnotation(task.id)
            task_annotation.init_from_db()

            # Create TaskData using CVAT's system
            task_data = TaskData(
                annotation_ir=task_annotation.ir_data,
                db_task=task,
                host=""
            )
        except Exception as e:
            # Fallback to simple approach if CVAT integration fails
            return self._create_simple_annotated_export(task, label)

        # Get all frames with annotations
        annotated_frames = {}

        # Process frames using CVAT's data structure
        for frame in task_data.group_by_frame(include_empty=False):
            frame_number = frame.idx

            # Filter by label if specified
            if label:
                frame_has_label = False

                # Check labeled shapes
                for shape in frame.labeled_shapes:
                    if shape.label == label.name:
                        frame_has_label = True
                        break

                # Check tags
                if not frame_has_label:
                    for tag in frame.tags:
                        if tag.label == label.name:
                            frame_has_label = True
                            break

                if not frame_has_label:
                    continue

            # Store frame data for processing
            annotated_frames[frame_number] = frame

        if not annotated_frames:
            # Return empty ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                metadata = {
                    "task_id": task.id,
                    "task_name": task.name,
                    "label_filter": label.name if label else "all_labels",
                    "total_frames": 0,
                    "export_type": "annotated_images",
                    "cvat_integrated": True
                }
                zip_file.writestr("metadata.json", json.dumps(metadata, indent=2))
            zip_buffer.seek(0)
            return zip_buffer

        # Create ZIP with annotated images
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:

            # Add metadata
            metadata = {
                "task_id": task.id,
                "task_name": task.name,
                "label_filter": label.name if label else "all_labels",
                "total_frames": len(annotated_frames),
                "export_type": "annotated_images",
                "cvat_integrated": True,
                "frames": list(annotated_frames.keys())
            }
            zip_file.writestr("metadata.json", json.dumps(metadata, indent=2))

            # Process each annotated frame
            for frame_number, frame_data in annotated_frames.items():
                try:
                    # Get original image using CVAT's frame provider
                    frame_provider = TaskFrameProvider(task)

                    # Get the frame
                    frame_response = frame_provider.get_frame(frame_number)

                    # Convert to PIL Image
                    image = Image.open(io.BytesIO(frame_response.data.getvalue()))

                    # Apply annotation overlay using CVAT's frame data
                    annotated_image = self._apply_cvat_annotations(image, frame_data, label)

                    # Save to ZIP
                    img_buffer = io.BytesIO()
                    annotated_image.save(img_buffer, format='PNG', optimize=True)

                    filename = f"frame_{frame_number:06d}.png"
                    zip_file.writestr(filename, img_buffer.getvalue())

                except Exception as e:
                    print(f"Error processing frame {frame_number}: {str(e)}")
                    continue

        zip_buffer.seek(0)
        return zip_buffer

    def _create_simple_annotated_export(self, task: Task, label: Optional[Label] = None) -> io.BytesIO:
        """Simple fallback export method using our existing logic."""

        # Import our existing working logic
        from .views import DownloadTaskFramesView

        # Create an instance and use its methods
        original_view = DownloadTaskFramesView()

        # Get annotated frames using our working method
        from cvat.apps.engine.models import Job
        jobs = Job.objects.filter(segment__task=task)

        all_annotated_frames = {}
        for job in jobs:
            job_frames = original_view._get_annotated_frames(job, label)
            if job_frames:
                all_annotated_frames[job.id] = job_frames

        # Create ZIP using our working method
        return original_view._create_task_frames_zip(task, all_annotated_frames, label)

    def _create_standard_cvat_export(self, task: Task, export_format: str) -> io.BytesIO:
        """Create standard CVAT export using the built-in export system."""

        # Use CVAT's export system
        task_annotation = TaskAnnotation(task.id)
        task_annotation.init_from_db()

        # Create temporary file for export
        with tempfile.NamedTemporaryFile() as temp_file:
            try:
                # Get exporter for the format
                exporter = make_exporter(export_format)

                # Export using CVAT's system
                task_annotation.export(
                    temp_file,
                    exporter,
                    host="",
                    save_images=True
                )

                # Read the exported file
                temp_file.seek(0)
                zip_buffer = io.BytesIO(temp_file.read())

            except Exception as e:
                # Fallback to empty ZIP with error info
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    error_info = {
                        "error": f"Export failed: {str(e)}",
                        "format": export_format,
                        "task_id": task.id
                    }
                    zip_file.writestr("error.json", json.dumps(error_info, indent=2))
                zip_buffer.seek(0)

        return zip_buffer

    def _apply_cvat_annotations(self, image: Image.Image, frame_data, label_filter: Optional[Label] = None) -> Image.Image:
        """Apply annotations to image using CVAT's frame data structure."""

        annotated_image = image.copy()
        draw = ImageDraw.Draw(annotated_image)

        # Load font
        font = self._get_font(size=24, bold=True)

        # Draw labeled shapes
        for shape in frame_data.labeled_shapes:
            # Filter by label if specified
            if label_filter and shape.label != label_filter.name:
                continue

            self._draw_cvat_shape(draw, shape, font)

        # Draw tags (if any visual representation needed)
        for tag in frame_data.tags:
            if label_filter and tag.label != label_filter.name:
                continue
            # Tags don't have visual representation, but we could add a watermark

        return annotated_image

    def _draw_cvat_shape(self, draw: ImageDraw.Draw, shape, font):
        """Draw a shape using CVAT's shape data structure with high quality rendering."""

        # Get shape properties
        shape_type = shape.type
        points = shape.points
        label_name = shape.label

        # Enhanced color palette with better visibility
        color = "#00FF00"  # Bright green for better contrast
        line_width = 4  # Increased line width for better visibility

        # Draw based on shape type with anti-aliasing simulation
        if shape_type == 'rectangle' and len(points) >= 4:
            x1, y1, x2, y2 = points[:4]
            self._draw_high_quality_rectangle(draw, x1, y1, x2, y2, color, line_width)
            text_position = (x1, y1 - 45)

        elif shape_type == 'polygon' and len(points) >= 6:
            polygon_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            self._draw_high_quality_polygon(draw, polygon_points, color, line_width)
            text_position = (polygon_points[0][0], polygon_points[0][1] - 45)

        elif shape_type == 'polyline' and len(points) >= 4:
            line_points = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
            self._draw_high_quality_polyline(draw, line_points, color, line_width)
            text_position = (line_points[0][0], line_points[0][1] - 45)

        elif shape_type == 'points':
            for i in range(0, len(points), 2):
                if i + 1 < len(points):
                    x, y = points[i], points[i+1]
                    self._draw_high_quality_point(draw, x, y, color)
                    if i == 0:
                        text_position = (x, y - 45)
        else:
            # Default handling for unknown shape types
            text_position = (10, 10)

        # Draw label text with high quality
        if 'text_position' in locals() and label_name:
            self._draw_high_quality_text(draw, text_position, label_name, font, color)

    def _draw_high_quality_rectangle(self, draw: ImageDraw.Draw, x1, y1, x2, y2, color, line_width):
        """Draw rectangle with anti-aliasing simulation."""
        # Draw multiple thin lines for smoother appearance
        for i in range(line_width):
            offset = i - line_width // 2
            draw.rectangle([x1 + offset, y1 + offset, x2 - offset, y2 - offset],
                         outline=color, width=1)

        # Add corner emphasis for better visibility
        corner_size = 8
        corners = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
        for cx, cy in corners:
            draw.rectangle([cx - corner_size//2, cy - corner_size//2,
                          cx + corner_size//2, cy + corner_size//2],
                         fill=color, outline="white", width=1)

    def _draw_high_quality_polygon(self, draw: ImageDraw.Draw, points, color, line_width):
        """Draw polygon with enhanced quality."""
        # Draw filled polygon with transparency effect
        for i in range(line_width):
            offset_points = [(x + i - line_width//2, y + i - line_width//2) for x, y in points]
            draw.polygon(offset_points, outline=color, width=1)

        # Add vertex markers
        for x, y in points:
            draw.ellipse([x-4, y-4, x+4, y+4], fill=color, outline="white", width=2)

    def _draw_high_quality_polyline(self, draw: ImageDraw.Draw, points, color, line_width):
        """Draw polyline with smooth connections."""
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]

            # Draw multiple lines for thickness with slight offsets
            for j in range(line_width):
                offset = j - line_width // 2
                draw.line([(x1 + offset, y1 + offset), (x2 + offset, y2 + offset)],
                         fill=color, width=1)

        # Add endpoint markers
        for x, y in [points[0], points[-1]]:
            draw.ellipse([x-6, y-6, x+6, y+6], fill=color, outline="white", width=2)

    def _draw_high_quality_point(self, draw: ImageDraw.Draw, x, y, color):
        """Draw point with enhanced visibility."""
        radius = 8
        # Draw multiple concentric circles for better visibility
        draw.ellipse([x-radius, y-radius, x+radius, y+radius],
                    fill=color, outline="white", width=3)
        draw.ellipse([x-radius//2, y-radius//2, x+radius//2, y+radius//2],
                    fill="white", outline=color, width=2)

    def _draw_high_quality_text(self, draw: ImageDraw.Draw, position, text, font, shape_color):
        """Draw text with premium quality and multiple enhancement layers."""

        x, y = position

        # Use larger font for better readability
        large_font = self._get_font(size=32, bold=True)

        # Get text dimensions
        text_bbox = draw.textbbox(position, text, font=large_font)
        padding = 16

        # Create enhanced background with gradient effect
        bg_bbox = (
            text_bbox[0] - padding,
            text_bbox[1] - padding,
            text_bbox[2] + padding,
            text_bbox[3] + padding
        )

        # Multi-layer background for premium appearance
        # 1. Shadow layer (offset)
        shadow_offset = 3
        shadow_bbox = (bg_bbox[0] + shadow_offset, bg_bbox[1] + shadow_offset,
                      bg_bbox[2] + shadow_offset, bg_bbox[3] + shadow_offset)
        draw.rectangle(shadow_bbox, fill=(0, 0, 0, 180))

        # 2. Main background with rounded corners effect
        draw.rectangle(bg_bbox, fill="black", outline="white", width=4)

        # 3. Inner border matching shape color
        inner_bbox = (bg_bbox[0] + 3, bg_bbox[1] + 3, bg_bbox[2] - 3, bg_bbox[3] - 3)
        draw.rectangle(inner_bbox, outline=shape_color, width=2)

        # 4. Text with outline for maximum clarity
        # Draw text outline (multiple passes for smooth outline)
        outline_offsets = [(-2, -2), (-2, 0), (-2, 2), (0, -2), (0, 2), (2, -2), (2, 0), (2, 2)]
        for dx, dy in outline_offsets:
            draw.text((position[0] + dx, position[1] + dy), text, fill="black", font=large_font)

        # 5. Main text in bright color
        draw.text(position, text, fill="#FFFF00", font=large_font)  # Bright yellow

        # 6. Add subtle highlight on top
        highlight_pos = (position[0], position[1] - 1)
        draw.text(highlight_pos, text, fill="white", font=large_font)

    def _draw_text_with_background(self, draw: ImageDraw.Draw, position, text, font):
        """Draw text with background for better visibility."""

        x, y = position

        # Get text dimensions
        text_bbox = draw.textbbox(position, text, font=font)
        padding = 8

        # Background rectangle
        bg_bbox = (
            text_bbox[0] - padding,
            text_bbox[1] - padding,
            text_bbox[2] + padding,
            text_bbox[3] + padding
        )

        # Draw background and text
        draw.rectangle(bg_bbox, fill="black", outline="white", width=2)
        draw.text(position, text, fill="yellow", font=font)

    def _get_font(self, size=24, bold=True):
        """Get high-quality font with comprehensive fallback system."""

        # Get the directory of this file for bundled fonts
        current_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(current_dir, 'fonts')

        # Try bundled fonts first (highest quality)
        bundled_fonts = []
        if bold:
            bundled_fonts = [
                os.path.join(fonts_dir, 'DejaVuSans-Bold.ttf'),
                os.path.join(fonts_dir, 'Arial-Bold.ttf'),
            ]
        else:
            bundled_fonts = [
                os.path.join(fonts_dir, 'DejaVuSans.ttf'),
                os.path.join(fonts_dir, 'Arial.ttf'),
            ]

        for font_path in bundled_fonts:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                continue

        # High-quality system fonts (prioritized list)
        system_fonts = [
            # macOS high-quality fonts
            "/System/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica Bold.ttc",
            "/System/Library/Fonts/SF-Pro-Display-Bold.otf",
            "/System/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SF-Pro-Display-Regular.otf",

            # Linux high-quality fonts
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-Regular.ttf",

            # Arch Linux paths
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/LiberationSans-Regular.ttf",
        ]

        for font_path in system_fonts:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                continue

        # Enhanced fallback with size adjustment
        try:
            # Try to load default with larger size for better quality
            default_font = ImageFont.load_default()
            # Note: PIL's default font doesn't support size parameter
            return default_font
        except Exception:
            # Ultimate fallback
            return ImageFont.load_default()


class CVATFormatsListView(APIView):
    """
    Endpoint to list available CVAT export formats.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get list of available export formats."""

        from cvat.apps.dataset_manager.views import get_export_formats

        try:
            formats = get_export_formats()
            format_list = []

            for fmt in formats:
                format_info = {
                    "name": fmt.DISPLAY_NAME,
                    "ext": fmt.EXT,
                    "enabled": fmt.ENABLED,
                }
                format_list.append(format_info)

            # Add our custom format
            format_list.append({
                "name": "Annotated Images",
                "ext": "ZIP",
                "enabled": True,
                "custom": True,
                "description": "Images with annotations overlaid"
            })

            return Response({
                "formats": format_list,
                "total": len(format_list)
            })

        except Exception as e:
            return Response(
                {'error': f'Failed to get formats: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
