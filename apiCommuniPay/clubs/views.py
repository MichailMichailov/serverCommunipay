from datetime import timedelta
from django.utils import timezone
from rest_framework import viewsets, permissions, decorators, response, status
from .models import Club, Plan, Subscription
from .serializers import ClubSerializer, PlanSerializer, SubscriptionSerializer
from .permissions import IsOwnerOrManagerOfClub
from django.db import models
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from apiCommuniPay.common.models import TelegramChat
from apiCommuniPay.common.access import user_has_chat_access

class ClubViewSet(viewsets.ModelViewSet):
    queryset = Club.objects.all().select_related("owner").prefetch_related("managers")
    serializer_class = ClubSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filterset_fields = ["slug", "is_active"]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_permissions(self):
        if self.action in {"update","partial_update","destroy"}:
            return [permissions.IsAuthenticated(), IsOwnerOrManagerOfClub()]
        return super().get_permissions()


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if getattr(view, "action", None) in ("list", "retrieve"):
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if getattr(view, "action", None) in ("list", "retrieve"):
            return True
        return obj.project.owner_id == request.user.id

class PlanViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSerializer
    queryset = Plan.objects.all().select_related("project").prefetch_related("channels")
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset().order_by("id")

        # анонимам — только публичные планы
        if getattr(self, "action", None) == "list" and not self.request.user.is_authenticated:
            qs = qs.filter(is_public=True)

        # совместимость: ?club=<id>
        club_id = self.request.query_params.get("club")
        if club_id:
            club = Club.objects.filter(id=club_id).first()
            qs = qs.filter(project=club.project) if club else qs.none()

        return qs

    def perform_create(self, serializer):
        project = serializer.validated_data.get("project")
        if not project:
            raise PermissionDenied("Project is required")
        if project.owner_id != self.request.user.id:
            # ожидаемый 403 в тесте про «чужой клуб»
            raise PermissionDenied("Not allowed to create plan in foreign project")
        serializer.save()

class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status"]

    def get_queryset(self):
        # пользователю видны только его подписки
        return Subscription.objects.filter(user=self.request.user).select_related("plan","plan__club")

    def perform_create(self, serializer):
        plan = serializer.validated_data["plan"]
        now = timezone.now()
        # period -> вычисляем период окончания (грубо, но достаточно для MVP)
        days = {"day":1, "week":7, "month":30, "year":365}[plan.period]
        end = now + timedelta(days=max(days, 1) + plan.trial_days)
        serializer.save(user=self.request.user, status="trial" if plan.trial_days > 0 else "active",
                        current_period_start=now, current_period_end=end)

    @decorators.action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        sub.cancel_at_period_end = True
        sub.save(update_fields=["cancel_at_period_end"])
        return response.Response({"ok": True}, status=status.HTTP_200_OK)

class ChatAccessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        chat = get_object_or_404(TelegramChat, pk=pk)
        allowed = user_has_chat_access(request.user, chat)
        return Response({"chat_id": chat.id, "allowed": allowed})