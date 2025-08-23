from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwnerOrManagerOfClub(BasePermission):
    """
    Для объектов, у которых есть атрибут club (Plan/Subscription),
    либо сам Club.
    """
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if getattr(u, "is_platform_staff", False):
            return True
        club = getattr(obj, "club", None)
        if club is None and obj.__class__.__name__ == "Club":
            club = obj
        if club is None:
            return False
        return club.owner_id == u.id or club.managers.filter(id=u.id).exists()
