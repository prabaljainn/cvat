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
