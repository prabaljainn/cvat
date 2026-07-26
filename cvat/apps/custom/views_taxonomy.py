# Copyright (C) 2026 CVAT Custom - Label Taxonomy
# SPDX-License-Identifier: MIT

"""
REST endpoints for the managed defect taxonomy (Tokyu label management):
  GET    /api/custom/taxonomy/labels/
  POST   /api/custom/taxonomy/labels/
  PATCH  /api/custom/taxonomy/labels/<id>/
  POST   /api/custom/taxonomy/labels/<id>/archive/
  POST   /api/custom/taxonomy/labels/<id>/restore/
  POST   /api/custom/taxonomy/sync/

Archive-only lifecycle: there is intentionally no DELETE route, so a
label that is already used by annotations can never be hard-deleted.
Sync only ever ADDS missing labels to the CVAT project; it never
deletes or renames existing CVAT labels (that would destroy
annotations), it just reports them as unmanaged.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.generics import ListCreateAPIView, UpdateAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from cvat.apps.engine.models import Label, Project

from .models import TaxonomyLabel
from .serializers import TaxonomyLabelSerializer

# Same policy source as the train-group schedule: DRF's IsAdminUser passes
# when user.is_staff is True. Swap this one list to change the write scope.
TAXONOMY_ADMIN_PERMISSIONS = [permissions.IsAdminUser]


class _TaxonomyPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class TaxonomyLabelListCreateView(ListCreateAPIView):
    """GET (any authenticated user) / POST (admin) /api/custom/taxonomy/labels/"""

    serializer_class = TaxonomyLabelSerializer
    pagination_class = _TaxonomyPagination
    filter_backends = []  # opt out of CVAT's IAM-aware filter chain

    def get_permissions(self):
        if self.request.method == "POST":
            return [cls() for cls in TAXONOMY_ADMIN_PERMISSIONS]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = TaxonomyLabel.objects.select_related("updated_by").all()
        search = self.request.query_params.get("search", "").strip()
        category = self.request.query_params.get("category", "").strip()
        archived = self.request.query_params.get("archived", "").strip().lower()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(category__icontains=search))
        if category:
            qs = qs.filter(category=category)
        if archived in ("true", "1"):
            qs = qs.filter(is_archived=True)
        elif archived in ("false", "0"):
            qs = qs.filter(is_archived=False)
        return qs

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)


class TaxonomyLabelDetailView(UpdateAPIView):
    """PATCH /api/custom/taxonomy/labels/<id>/ - edit name/color/category/priority."""

    permission_classes = TAXONOMY_ADMIN_PERMISSIONS
    serializer_class = TaxonomyLabelSerializer
    queryset = TaxonomyLabel.objects.all()
    http_method_names = ["patch", "options"]

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class _ArchiveFlagView(APIView):
    """Shared POST handler flipping is_archived one way."""

    permission_classes = TAXONOMY_ADMIN_PERMISSIONS
    target_archived: bool

    def post(self, request, pk):
        label = get_object_or_404(TaxonomyLabel, pk=pk)
        label.is_archived = self.target_archived
        label.updated_by = request.user
        label.save(update_fields=["is_archived", "updated_by", "updated_date"])
        return Response(TaxonomyLabelSerializer(label).data)


class TaxonomyLabelArchiveView(_ArchiveFlagView):
    """POST /api/custom/taxonomy/labels/<id>/archive/"""

    target_archived = True


class TaxonomyLabelRestoreView(_ArchiveFlagView):
    """POST /api/custom/taxonomy/labels/<id>/restore/"""

    target_archived = False


class TaxonomySyncView(APIView):
    """POST /api/custom/taxonomy/sync/ - body {"project_id": <id>}.

    Adds every active taxonomy label missing from the project (matched by
    name) with the taxonomy color. Existing CVAT labels are never touched.
    """

    permission_classes = TAXONOMY_ADMIN_PERMISSIONS

    def post(self, request):
        try:
            project_id = int(request.data.get("project_id"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "project_id (integer) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project = get_object_or_404(Project, pk=project_id)

        with transaction.atomic():
            existing_names = set(
                Label.objects.filter(project=project, parent__isnull=True)
                .values_list("name", flat=True)
            )
            created, already_present = [], []
            skipped_archived, archived_but_present = [], []
            taxonomy_names = set()
            for entry in TaxonomyLabel.objects.order_by("priority", "name"):
                taxonomy_names.add(entry.name)
                if entry.is_archived:
                    if entry.name in existing_names:
                        archived_but_present.append(entry.name)
                    else:
                        skipped_archived.append(entry.name)
                    continue
                # get_or_create instead of a name-set precheck so a label
                # added concurrently (or through the CVAT project UI) lands
                # in already_present instead of raising IntegrityError.
                _, was_created = Label.objects.get_or_create(
                    project=project,
                    name=entry.name,
                    parent=None,
                    defaults={"color": entry.color},
                )
                if was_created:
                    created.append(entry.name)
                else:
                    already_present.append(entry.name)
            if created:
                # Mirror CVAT's own label-mutation path: bump the project AND
                # every child task/job so label caches and exports refresh.
                from cvat.apps.engine.serializers import ProjectWriteSerializer

                project.touch()
                ProjectWriteSerializer(project).update_child_objects_on_labels_update(
                    project
                )

        return Response(
            {
                "project_id": project.id,
                "created": created,
                "already_present": already_present,
                "skipped_archived": skipped_archived,
                "archived_but_present": archived_but_present,
                "unmanaged": sorted(existing_names - taxonomy_names),
            }
        )
