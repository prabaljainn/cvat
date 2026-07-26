# Copyright (C) 2026 CVAT Custom - User Admin Console
# SPDX-License-Identifier: MIT

"""
REST endpoints for the customer-admin user management console:
  GET    /api/custom/user-admin/users/
  POST   /api/custom/user-admin/users/
  PATCH  /api/custom/user-admin/users/<id>/
  POST   /api/custom/user-admin/users/<id>/deactivate/
  POST   /api/custom/user-admin/users/<id>/reactivate/
  POST   /api/custom/user-admin/users/<id>/reset-password/
  GET    /api/custom/user-admin/audit/

CVAT's native /api/users hides email and last_login from non-superusers,
has no create action, and audits to Clickhouse without a query surface.
This console fills those gaps for the single-tenant deployments.
Role model: 'admin' maps to CVAT's admin privilege group + is_staff,
'user' to the user group. Group membership is checked per request, so
role changes take effect immediately. Deactivated users cannot log in
(Django's ModelBackend rejects inactive users).
"""

from __future__ import annotations

import logging
import smtplib

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from cvat.apps.iam.forms import ResetPasswordFormEx

from .models import UserAdminAuditLog
from .serializers import (
    UserAdminAuditLogSerializer,
    UserAdminUserCreateSerializer,
    UserAdminUserSerializer,
)

logger = logging.getLogger(__name__)

USER_ADMIN_PERMISSIONS = [permissions.IsAdminUser]

ROLE_ADMIN = getattr(settings, "IAM_ADMIN_ROLE", "admin")
ROLE_USER = getattr(settings, "IAM_DEFAULT_ROLE", "user")


class _UserAdminPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


def _apply_role(user: User, role: str) -> None:
    """Map the console role onto CVAT's privilege source (groups + is_staff).

    All IAM role groups are cleared first: the IAM middleware resolves the
    highest-priority group a user belongs to, so a leftover membership
    (e.g. worker) would silently keep or escalate privileges.
    """
    role_names = list(getattr(settings, "IAM_ROLES", [ROLE_ADMIN, ROLE_USER, "worker"]))
    user.groups.remove(*Group.objects.filter(name__in=role_names))
    target_name = ROLE_ADMIN if role == ROLE_ADMIN else ROLE_USER
    target_group, _ = Group.objects.get_or_create(name=target_name)
    user.groups.add(target_group)
    user.is_staff = role == ROLE_ADMIN
    user.save(update_fields=["is_staff"])


def _audit(actor: User, target: User, action: str, changes: dict | None = None) -> None:
    UserAdminAuditLog.objects.create(
        actor=actor,
        target=target,
        target_username=target.username,
        action=action,
        changes=changes or {},
    )


def _other_active_admin_exists(excluding: User) -> bool:
    return (
        User.objects.filter(is_active=True, is_staff=True)
        .exclude(pk=excluding.pk)
        .exists()
    )


class UserAdminListCreateView(ListCreateAPIView):
    """GET list with filters / POST create - /api/custom/user-admin/users/"""

    permission_classes = USER_ADMIN_PERMISSIONS
    pagination_class = _UserAdminPagination
    filter_backends = []  # opt out of CVAT's IAM-aware filter chain

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserAdminUserCreateSerializer
        return UserAdminUserSerializer

    def get_queryset(self):
        qs = User.objects.prefetch_related("groups").order_by("username")
        search = self.request.query_params.get("search", "").strip()
        role = self.request.query_params.get("role", "").strip().lower()
        user_status = self.request.query_params.get("status", "").strip().lower()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        if role == ROLE_ADMIN:
            qs = qs.filter(Q(is_staff=True) | Q(groups__name=ROLE_ADMIN)).distinct()
        elif role == ROLE_USER:
            qs = qs.filter(is_staff=False).exclude(groups__name=ROLE_ADMIN)
        if user_status == "active":
            qs = qs.filter(is_active=True)
        elif user_status == "inactive":
            qs = qs.filter(is_active=False)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        password = data.pop("password", None)
        role = data.pop("role", ROLE_USER)

        user = User(**data)
        if password is not None:
            # Pass the candidate user so the similarity validator can
            # reject passwords echoing the username or email.
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                return Response(
                    {"password": exc.messages}, status=status.HTTP_400_BAD_REQUEST
                )
            user.set_password(password)
        else:
            # The user sets their own password via the reset email flow.
            user.set_unusable_password()

        with transaction.atomic():
            user.save()
            _apply_role(user, role)
            _audit(
                request.user, user, UserAdminAuditLog.ActionChoices.CREATE, {"role": role}
            )
        return Response(
            UserAdminUserSerializer(user).data, status=status.HTTP_201_CREATED
        )


class UserAdminDetailView(APIView):
    """PATCH /api/custom/user-admin/users/<id>/ - email, names, role."""

    permission_classes = USER_ADMIN_PERMISSIONS

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        editable = {
            field: request.data[field]
            for field in ("email", "first_name", "last_name")
            if field in request.data
        }
        serializer = UserAdminUserSerializer(user, data=editable, partial=True)
        serializer.is_valid(raise_exception=True)
        changes = {
            field: value
            for field, value in serializer.validated_data.items()
            if getattr(user, field) != value
        }

        role = request.data.get("role")
        if role is not None:
            if role not in (ROLE_ADMIN, ROLE_USER):
                return Response(
                    {"detail": f"role must be '{ROLE_ADMIN}' or '{ROLE_USER}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            current_role = ROLE_ADMIN if user.is_staff else ROLE_USER
            if role == current_role:
                role = None  # no-op change, keep the audit trail clean
            elif role == ROLE_USER and user.is_staff:
                # Demotion must honor the same invariants as deactivation.
                if user.pk == request.user.pk:
                    return Response(
                        {"detail": "You cannot demote your own account."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not _other_active_admin_exists(user):
                    return Response(
                        {"detail": "Cannot demote the last active admin."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if role is not None:
            changes["role"] = role

        with transaction.atomic():
            serializer.save()
            if role is not None:
                _apply_role(user, role)
            if changes:
                _audit(
                    request.user, user, UserAdminAuditLog.ActionChoices.UPDATE, changes
                )
        user.refresh_from_db()
        return Response(UserAdminUserSerializer(user).data)


class UserAdminDeactivateView(APIView):
    """POST /api/custom/user-admin/users/<id>/deactivate/"""

    permission_classes = USER_ADMIN_PERMISSIONS

    def post(self, request, pk):
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=pk)
            if user.pk == request.user.pk:
                return Response(
                    {"detail": "You cannot deactivate your own account."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if user.is_staff and not _other_active_admin_exists(user):
                return Response(
                    {"detail": "Cannot deactivate the last active admin."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.is_active = False
            user.save(update_fields=["is_active"])
            _audit(request.user, user, UserAdminAuditLog.ActionChoices.DEACTIVATE)
        return Response(UserAdminUserSerializer(user).data)


class UserAdminReactivateView(APIView):
    """POST /api/custom/user-admin/users/<id>/reactivate/"""

    permission_classes = USER_ADMIN_PERMISSIONS

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.is_active = True
        user.save(update_fields=["is_active"])
        _audit(request.user, user, UserAdminAuditLog.ActionChoices.REACTIVATE)
        return Response(UserAdminUserSerializer(user).data)


class UserAdminResetPasswordView(APIView):
    """POST /api/custom/user-admin/users/<id>/reset-password/

    Uses CVAT's ResetPasswordFormEx: the allauth base form reverses
    allauth URLs that CVAT never mounts (NoReverseMatch) and would use
    the sites-framework domain in the link. The token is issued for
    exactly this user even when several accounts share the email
    address. email_sent reports the actual outcome and the audit row is
    written either way.
    """

    permission_classes = USER_ADMIN_PERMISSIONS

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if not user.email:
            return Response(
                {"detail": "User has no email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response(
                {"detail": "Deactivated users cannot receive password resets."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = ResetPasswordFormEx(data={"email": user.email})
        email_sent = False
        if form.is_valid():
            # The form resolves users by email, which is not unique on the
            # Django user model; pin it to the account being managed.
            form.users = [user]
            save_options = {}
            domain = getattr(settings, "UI_HOST", None)
            if domain and getattr(settings, "UI_PORT", None):
                domain = f"{domain}:{settings.UI_PORT}"
            if domain:
                save_options["domain_override"] = domain
            try:
                form.save(request, **save_options)
                email_sent = True
            except (smtplib.SMTPException, OSError):
                logger.exception(
                    "Password reset email failed for user %s", user.username
                )
        _audit(
            request.user,
            user,
            UserAdminAuditLog.ActionChoices.PASSWORD_RESET,
            {"email_sent": email_sent},
        )
        return Response({"email_sent": email_sent})


class UserAdminAuditListView(ListAPIView):
    """GET /api/custom/user-admin/audit/?target_id=&action="""

    permission_classes = USER_ADMIN_PERMISSIONS
    serializer_class = UserAdminAuditLogSerializer
    pagination_class = _UserAdminPagination
    filter_backends = []

    def get_queryset(self):
        qs = UserAdminAuditLog.objects.select_related("actor", "target").all()
        target_id = self.request.query_params.get("target_id", "").strip()
        action = self.request.query_params.get("action", "").strip()
        if target_id:
            if not target_id.isdigit():
                return qs.none()
            qs = qs.filter(target_id=int(target_id))
        if action:
            qs = qs.filter(action=action)
        return qs
