# Copyright (C) 2026 CVAT Custom — Train Group Schedule
# SPDX-License-Identifier: MIT

"""
REST endpoints for the train_id → group schedule:
  GET    /api/train-groups/mappings/
  GET    /api/train-groups/mappings/template.csv
  GET    /api/train-groups/mappings/export.csv
  POST   /api/train-groups/mappings/upload/
  GET    /api/train-groups/groups/                 (alias for tasks-summary.available_groups)
  GET    /api/train-groups/versions/
  GET    /api/train-groups/versions/<id>/
  POST   /api/train-groups/versions/<id>/rollback/
"""

from __future__ import annotations

from rest_framework import permissions

# --- Permission policy (single source of truth — swap one line to change scope) ---
# DRF's IsAdminUser passes when user.is_staff is True. Superusers created via
# `createsuperuser` are also is_staff, so both groups pass. To restrict further
# (e.g., to a custom Django Group or a CVAT IAM role), replace this list.
MAPPING_ADMIN_PERMISSIONS = [permissions.IsAdminUser]


from django.db.models import Q
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from .models import TrainGroupMapping
from .serializers import TrainGroupMappingSerializer


class _MappingPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class MappingsListView(ListAPIView):
    """GET /api/train-groups/mappings/?search=&group=&page=&page_size="""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TrainGroupMappingSerializer
    pagination_class = _MappingPagination

    def get_queryset(self):
        qs = TrainGroupMapping.objects.select_related("updated_by").order_by("train_id")
        search = self.request.query_params.get("search", "").strip()
        group = self.request.query_params.get("group", "").strip()
        if group:
            qs = qs.filter(group=group)
        if search:
            qs = qs.filter(Q(train_id__icontains=search) | Q(group__icontains=search))
        return qs


import csv as _csv
from io import StringIO

from django.http import HttpResponse
from rest_framework.views import APIView


_TEMPLATE_CSV = (
    "train_id,group\n"
    "3101F,A\n"
    "3102F,B\n"
    "3103F,C\n"
)


class MappingTemplateCsvView(APIView):
    """GET /api/train-groups/mappings/template.csv — blank example CSV."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        resp = HttpResponse(_TEMPLATE_CSV, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="train_group_template.csv"'
        return resp


class MappingExportCsvView(APIView):
    """GET /api/train-groups/mappings/export.csv — current mapping as CSV."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        buf = StringIO()
        writer = _csv.writer(buf)
        writer.writerow(["train_id", "group"])
        for m in TrainGroupMapping.objects.order_by("train_id").values_list("train_id", "group"):
            writer.writerow(m)
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="train_group_mapping.csv"'
        return resp


from dataclasses import asdict

from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.response import Response

from .train_group_parser import (
    parse_csv, parse_xlsx, parse_pasted, compute_diff, apply_upload,
)

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_PASTED_BYTES = 1 * 1024 * 1024  # 1 MB


def _is_truthy(val) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


class UploadView(APIView):
    """POST /api/train-groups/mappings/upload/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        comment = (request.data.get("comment") or "").strip()
        dry_run = _is_truthy(request.data.get("dry_run"))

        # ---- 1. Resolve input mode and parse ----
        if "file" in request.FILES:
            upload = request.FILES["file"]
            if upload.size > _MAX_FILE_BYTES:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": f"file exceeds {_MAX_FILE_BYTES // 1024 // 1024} MB"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            data = upload.read()
            name = (upload.name or "").lower()

            if name.endswith(".xlsx"):
                rows, errors = parse_xlsx(data)
                source_format = "xlsx"
                # Normalize raw_input to canonical CSV for storage
                raw_input_text = "train_id,group\n" + "".join(
                    f"{r.train_id},{r.group}\n" for r in rows
                )
            elif name.endswith(".csv") or name == "":
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    return Response(
                        {"errors": [{"line": 0, "reason": "file is not valid UTF-8"}]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                rows, errors = parse_csv(text)
                source_format = "csv"
                raw_input_text = text
            else:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": "unsupported file extension; expected .csv or .xlsx"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        elif "text" in request.data:
            text = request.data.get("text") or ""
            if len(text.encode("utf-8")) > _MAX_PASTED_BYTES:
                return Response(
                    {"errors": [{"line": 0,
                                 "reason": f"pasted text exceeds {_MAX_PASTED_BYTES // 1024} KB"}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows, errors = parse_pasted(text)
            source_format = "paste"
            raw_input_text = "train_id,group\n" + "".join(
                f"{r.train_id},{r.group}\n" for r in rows
            )

        else:
            return Response(
                {"errors": [{"line": 0,
                             "reason": "expected multipart 'file' or JSON 'text'"}]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if errors:
            return Response(
                {"errors": [asdict(e) for e in errors]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---- 2. Diff for warnings ----
        diff = compute_diff(rows, TrainGroupMapping.objects.all())
        warnings = self._generate_warnings(rows, diff)

        # ---- 3. Dry-run short-circuit ----
        if dry_run:
            return Response({
                "version": None,
                "diff": diff,
                "warnings": warnings,
            })

        # ---- 4. Apply ----
        try:
            version = apply_upload(
                rows=rows, user=request.user, comment=comment,
                raw_input_text=raw_input_text, source_format=source_format,
            )
        except Exception as exc:
            return Response(
                {"errors": [{"line": 0, "reason": f"apply failed: {exc}"}]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "version": version.version_no,
            "diff": version.diff_summary,
            "warnings": warnings,
        })

    def _generate_warnings(self, rows, diff):
        """Non-blocking informational warnings shown to the admin."""
        from .models import TaskTrainMetadata

        warnings = []
        train_ids_in_csv = {r.train_id for r in rows}

        # Trains in CSV with no existing task metadata yet
        existing_with_meta = set(
            TaskTrainMetadata.objects.filter(train_id__in=train_ids_in_csv)
            .values_list("train_id", flat=True)
        )
        unused_in_csv = train_ids_in_csv - existing_with_meta
        if unused_in_csv:
            warnings.append({
                "code": "trains_with_no_tasks",
                "message": f"{len(unused_in_csv)} trains in CSV have no tasks yet",
                "sample": sorted(unused_in_csv)[:10],
            })

        # Tasks that will become Ungrouped (their train_id is being removed)
        removed_train_ids = {r["train_id"] for r in diff["removed"]}
        affected_task_count = TaskTrainMetadata.objects.filter(
            train_id__in=removed_train_ids,
        ).count()
        if affected_task_count:
            warnings.append({
                "code": "tasks_becoming_ungrouped",
                "message": f"{affected_task_count} tasks will become Ungrouped",
                "sample": sorted(removed_train_ids)[:10],
            })

        return warnings


from rest_framework.generics import RetrieveAPIView

from .models import TrainGroupMappingVersion
from .serializers import (
    TrainGroupMappingVersionListSerializer,
    TrainGroupMappingVersionDetailSerializer,
)


class VersionsListView(ListAPIView):
    """GET /api/train-groups/versions/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    serializer_class = TrainGroupMappingVersionListSerializer
    pagination_class = _MappingPagination

    def get_queryset(self):
        return (
            TrainGroupMappingVersion.objects
            .select_related("uploaded_by")
            .order_by("-version_no")
        )


class VersionDetailView(RetrieveAPIView):
    """GET /api/train-groups/versions/<version_no>/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS
    serializer_class = TrainGroupMappingVersionDetailSerializer
    queryset = TrainGroupMappingVersion.objects.all()
    lookup_field = "version_no"


from django.shortcuts import get_object_or_404


class RollbackView(APIView):
    """POST /api/train-groups/versions/<version_no>/rollback/"""
    permission_classes = MAPPING_ADMIN_PERMISSIONS

    def post(self, request, version_no: int):
        source = get_object_or_404(TrainGroupMappingVersion, version_no=version_no)
        comment = (request.data.get("comment") or f"Rollback to v{source.version_no}").strip()

        # Re-parse the stored csv_text — it's always canonical CSV
        rows, errors = parse_csv(source.csv_text)
        if errors:
            return Response(
                {"errors": [asdict(e) for e in errors]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        version = apply_upload(
            rows=rows, user=request.user, comment=comment,
            raw_input_text=source.csv_text, source_format="rollback",
            source_version=source,
        )
        return Response({
            "version": version.version_no,
            "source_version": source.version_no,
            "diff": version.diff_summary,
        })
