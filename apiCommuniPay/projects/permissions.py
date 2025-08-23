from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import ProjectMember


class IsProjectMember(BasePermission):
    """
    Доступ к проекту только участникам (любой роли).
    """

    def has_object_permission(self, request, view, obj):
        return ProjectMember.objects.filter(project=obj, user=request.user).exists()


class CanManageProject(BasePermission):
    """
    Право на изменение/удаление проекта только у owner/admin.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return ProjectMember.objects.filter(project=obj, user=request.user).exists()
        return ProjectMember.objects.filter(
            project=obj, user=request.user, role__in=[ProjectMember.Role.OWNER, ProjectMember.Role.ADMIN]
        ).exists()
