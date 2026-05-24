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
