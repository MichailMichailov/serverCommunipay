from datetime import timedelta
from django.utils import timezone
from rest_framework import viewsets, permissions, decorators, response, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import Plan, Subscription
from .serializers import PlanSerializer, SubscriptionSerializer  # ClubSerializer removed

from apiCommuniPay.common.models import TelegramChat


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Разрешение: только владелец проекта может изменять объекты, чтение доступно всем.

    Ожидается, что у объекта (например, Plan) есть поле `project` с `owner`.
    """

    def has_permission(self, request, view):
        if getattr(view, "action", None) in ("list", "retrieve"):
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if getattr(view, "action", None) in ("list", "retrieve"):
            return True
        project = getattr(obj, "project", None)
        owner_id = getattr(getattr(project, "owner", None), "id", None)
        return owner_id == getattr(request.user, "id", None)


class PlanViewSet(viewsets.ModelViewSet):
    """
    CRUD по тарифам (Plan).

    Фильтры:
    - ?project=<uuid> — только тарифы выбранного проекта
    - ?chat=<chat_pk> — тарифы, привязанные к указанному TelegramChat
    - если пользователь не аутентифицирован и action==list — возвращаются только публичные тарифы
    """

    serializer_class = PlanSerializer
    queryset = Plan.objects.all().select_related("project").order_by("id")
    permission_classes = [IsOwnerOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()

        # анонимам — только публичные планы при списке
        if getattr(self, "action", None) == "list" and not self.request.user.is_authenticated:
            qs = qs.filter(is_public=True)

        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)

        chat_pk = self.request.query_params.get("chat")
        if chat_pk:
            qs = qs.filter(channels__id=chat_pk)

        return qs

    def perform_create(self, serializer):
        project = serializer.validated_data.get("project")
        if not project:
            raise permissions.PermissionDenied("Project is required")
        if getattr(project.owner, "id", None) != getattr(self.request.user, "id", None):
            raise permissions.PermissionDenied("Not allowed to create plan in foreign project")
        serializer.save()


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    Подписки текущего пользователя.

    При создании подписки здесь не вычисляется срок действия —
    ожидается, что это сделает бизнес-логика/платёжный обработчик
    или поле `ends_at` будет заполнено сериализатором/данными запроса.
    """

    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status"]

    def get_queryset(self):
        return (
            Subscription.objects
            .filter(user=self.request.user)
            .select_related("plan", "plan__project")
            .order_by("-created_at", "id")
        )

    def perform_create(self, serializer):
        # по умолчанию активная, без автоматического вычисления `ends_at`
        serializer.save(user=self.request.user, status=self.request.data.get("status", "active"))

    @decorators.action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sub = self.get_object()
        # простой сценарий — помечаем как отменённую сразу
        sub.status = "canceled"
        sub.save(update_fields=["status"])
        return response.Response({"ok": True}, status=status.HTTP_200_OK)


class ChatAccessView(APIView):
    """
    Простая проверка доступа пользователя к Telegram-чату на основе активных подписок.

    Пользователь имеет доступ, если существует *активная* подписка на план,
    который привязан к этому чату через M2M `Plan.channels`.
    Под активной понимаем: `status == 'active'` И (`ends_at` пусто ИЛИ `ends_at > now()`).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk: int):
        chat = get_object_or_404(TelegramChat, pk=pk)
        now = timezone.now()
        allowed = Subscription.objects.filter(
            user=request.user,
            status="active",
            plan__channels=chat,
        ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)).exists()
        return Response({"chat_id": chat.id, "allowed": allowed})