from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User


def is_internal(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") in set(User.INTERNAL_ROLES))
    )


def is_manager(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "role", "") in set(User.MANAGER_ROLES)
            or getattr(user, "role", "") in set(User.SUPPORT_ROLE_ALIASES)
        )
    )


def is_read_only(user):
    return bool(
        user
        and user.is_authenticated
        and getattr(user, "role", "") in set(User.READ_ONLY_ROLES)
    )


class IsAuthenticatedSavUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsInternalUser(BasePermission):
    def has_permission(self, request, view):
        return is_internal(request.user)


class IsManagerUser(BasePermission):
    def has_permission(self, request, view):
        return is_manager(request.user)


class ReadOnlyForClients(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return is_internal(request.user)


class ReadOnlyForAuditors(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return not is_read_only(request.user)
