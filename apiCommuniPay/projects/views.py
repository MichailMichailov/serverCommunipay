from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Project, ProjectMember
from .permissions import IsProjectMember, CanManageProject
from .serializers import ProjectSerializer, ProjectMemberSerializer

User = get_user_model()


class ProjectViewSet(viewsets.ModelViewSet):
    """
    /api/projects/ — список проектов, где текущий пользователь участник.
    POST создаёт проект и делает автора владельцем (owner).
    """
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated,]
    lookup_field = "id"  # UUID

    def get_queryset(self):
        user = self.request.user
        return (
            Project.objects
            .filter(memberships__user=user)
            .select_related("owner")
            .prefetch_related("memberships")
            .distinct()
        )

    def get_permissions(self):
        if self.action in ["retrieve", "members", "add_member", "update_member", "remove_member", "transfer_ownership"]:
            return [IsAuthenticated(), IsProjectMember()]
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsAuthenticated(), CanManageProject()]
        return [IsAuthenticated()]

    @action(methods=["get"], detail=True, url_path="members-list")
    def members(self, request, id=None):
        project = self.get_object()
        qs = project.memberships.select_related("user").order_by("joined_at")
        return Response(ProjectMemberSerializer(qs, many=True).data)

    @action(methods=["post"], detail=True, url_path="members")
    def add_member(self, request, id=None):
        """
        Добавить участника (admin/owner). body: {"user": <id>, "role": "editor"}
        """
        project = self.get_object()
        # проверим права
        if not ProjectMember.objects.filter(
            project=project, user=request.user, role__in=[ProjectMember.Role.OWNER, ProjectMember.Role.ADMIN]
        ).exists():
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        ser = ProjectMemberSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        role = ser.validated_data["role"]

        if ProjectMember.objects.filter(project=project, user=user).exists():
            return Response({"detail": "User already a member"}, status=status.HTTP_400_BAD_REQUEST)

        member = ProjectMember.objects.create(project=project, user=user, role=role)
        return Response(ProjectMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(methods=["patch"], detail=True, url_path="members/(?P<member_id>[^/.]+)")
    def update_member(self, request, member_id=None, id=None):
        """
        Изменить роль участника (admin/owner). Нельзя понизить текущего owner напрямую —
        для этого есть отдельный transfer_ownership.
        """
        project = self.get_object()
        if not ProjectMember.objects.filter(
            project=project, user=request.user, role__in=[ProjectMember.Role.OWNER, ProjectMember.Role.ADMIN]
        ).exists():
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            member = project.memberships.get(pk=member_id)
        except ProjectMember.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if member.role == ProjectMember.Role.OWNER:
            return Response({"detail": "Use transfer_ownership to change owner"}, status=400)

        ser = ProjectMemberSerializer(member, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ProjectMemberSerializer(member).data)

    @action(methods=["delete"], detail=True, url_path="members/(?P<member_id>[^/.]+)")
    def remove_member(self, request, member_id=None, id=None):
        """
        Удалить участника (admin/owner). Нельзя удалить владельца.
        """
        project = self.get_object()
        if not ProjectMember.objects.filter(
            project=project, user=request.user, role__in=[ProjectMember.Role.OWNER, ProjectMember.Role.ADMIN]
        ).exists():
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            member = project.memberships.get(pk=member_id)
        except ProjectMember.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if member.role == ProjectMember.Role.OWNER or member.user_id == project.owner_id:
            return Response({"detail": "Cannot remove owner"}, status=400)

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["post"], detail=True)
    @transaction.atomic
    def transfer_ownership(self, request, id=None):
        """
        Передача владения: body: {"user": <id>}
        """
        project = self.get_object()

        # только текущий владелец
        if not ProjectMember.objects.filter(project=project, user=request.user, role=ProjectMember.Role.OWNER).exists():
            return Response({"detail": "Only owner can transfer ownership"}, status=403)

        new_owner_id = request.data.get("user")
        try:
            new_owner_member = project.memberships.get(user_id=new_owner_id)
        except ProjectMember.DoesNotExist:
            return Response({"detail": "User is not a project member"}, status=400)

        # понижаем старого владельца до admin
        old_owner_id = project.owner_id
        ProjectMember.objects.filter(project=project, user_id=old_owner_id).update(role=ProjectMember.Role.ADMIN)

        # назначаем нового
        new_owner_member.role = ProjectMember.Role.OWNER
        new_owner_member.save(update_fields=["role"])

        project.owner_id = new_owner_id
        project.save(update_fields=["owner"])

        return Response(ProjectSerializer(project, context={"request": request}).data)
