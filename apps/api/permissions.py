"""API permissions.

Every view declares the capability it needs; this class turns that into a
permission check against the role table in ``apps.accounts.permissions``.
"""

from rest_framework import permissions

from apps.accounts.permissions import has_capability


class HasCapability(permissions.BasePermission):
    """Allow the request when the user's role holds ``view.capability``.

    A view declares the capability it needs. For a read, that is
    ``read_capability`` when it is set and ``capability`` otherwise - the
    fallback is deliberately strict, because a view that forgets to declare a
    read capability should not become open to every signed-in user.

    ``action_capabilities`` lets a view give one action a different
    requirement from the rest: generating a forecast, for instance, is a
    mess manager's job, while editing a forecast's configuration is the
    administrator's.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view) -> bool:
        capability = getattr(view, "capability", None)
        action = getattr(view, "action", None)

        action_map = getattr(view, "action_capabilities", None) or {}
        if action and action in action_map:
            capability = action_map[action]

        if capability is None:
            return True

        if request.method in permissions.SAFE_METHODS:
            read_capability = getattr(view, "read_capability", None)
            if read_capability is None:
                read_capability = capability
            return has_capability(request.user, read_capability)
        return has_capability(request.user, capability)


class IsKitchenStaffOrManager(permissions.BasePermission):
    """Kitchen screens are for staff of that hall, managers and administrators."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated:
            return False
        if user.role in {"MESS_MANAGER", "ADMINISTRATOR", "MESS_ADMIN"}:
            return True
        if user.role == "KITCHEN_STAFF":
            hall = getattr(view, "hall", None)
            if hall is None or user.hall_id in (None, hall.id):
                return True
        return False
