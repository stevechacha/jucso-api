from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated

from core.models import UserRole


class PortalAccessPermission(permissions.BasePermission):
    """Block portal actions until a temporary staff password has been changed."""

    message = "You must change your temporary password before continuing."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return True
        if not getattr(user, "must_change_password", False):
            return True
        url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
        return url_name in {"me", "change-password"}


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.STUDENT
        )


class IsMinister(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.MINISTER
        )


class IsExecutive(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.EXECUTIVE
        )


class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN
        )


class IsLeader(permissions.BasePermission):
    """Minister, executive, or admin."""

    LEADER_ROLES = frozenset({UserRole.MINISTER, UserRole.EXECUTIVE, UserRole.ADMIN})

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in self.LEADER_ROLES
        )


# Use on every authenticated view (DRF replaces DEFAULT_PERMISSION_CLASSES when set).
AUTHENTICATED = (IsAuthenticated, PortalAccessPermission)
