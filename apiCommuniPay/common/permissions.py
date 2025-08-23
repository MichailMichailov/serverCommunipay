from rest_framework.permissions import BasePermission, SAFE_METHODS

class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS

class IsPlatformStaff(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and getattr(u, "is_platform_staff", False))

class IsOwnerOfObjectOrPlatformStaff(BasePermission):
    """
    Требует у объекта поле .owner
    """
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if getattr(u, "is_platform_staff", False):
            return True
        return getattr(obj, "owner_id", None) == u.id

class IsOwnerOrManagerOfClub(BasePermission):
    """
    Ищет club у obj или через view.get_club(obj)
    """
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if getattr(u, "is_platform_staff", False):
            return True
        club = getattr(obj, "club", None)
        if club is None and hasattr(view, "get_club"):
            club = view.get_club(obj)
        if club is None:
            return False
        if club.owner_id == u.id:
            return True
        try:
            return club.managers.filter(id=u.id).exists()
        except Exception:
            return False

class IsProjectOwner(BasePermission):
    def has_permission(self, request, view):
        project = getattr(view, "project", None)
        return bool(project and request.user.is_authenticated and project.owner_id == request.user.id)

