
from rest_framework.permissions import BasePermission



class IsStaff(BasePermission):
    """
    Allows access only to authenticated users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)

