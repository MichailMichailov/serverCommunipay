from rest_framework import decorators, status, permissions, generics
from rest_framework.response import Response

from django.conf import settings
from django.shortcuts import get_object_or_404
from apiCommuniPay.projects.models import Project
from .models import TelegramChat, ChatLinkIntent
from .serializers import TelegramChatSerializer, ChatLinkIntentCreateSerializer, ChatLinkIntentResponseSerializer
from .permissions import IsProjectOwner

BOT_USERNAME = getattr(settings, "TELEGRAM_BOT_USERNAME", "")

@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.AllowAny])
def healthz(_request):
    return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectContextMixin:
    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(Project, pk=kwargs["project_id"])
        return super().dispatch(request, *args, **kwargs)

class ProjectChannelsList(ProjectContextMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsProjectOwner]
    serializer_class = TelegramChatSerializer

    def get_queryset(self):
        return TelegramChat.objects.filter(project=self.project).order_by("-created_at")

class CreateLinkIntent(ProjectContextMixin, generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated, IsProjectOwner]
    serializer_class = ChatLinkIntentCreateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # ttl from payload (validated by serializer)
        ttl = serializer.validated_data["ttl_minutes"]

        # 2) определить Telegram user id инициатора (из payload или из профиля пользователя)
        tg_user_id = (
            serializer.validated_data.get("tg_user_id")
            if hasattr(serializer, "validated_data") else None
        )
        if tg_user_id is None:
            tg_user_id = (
                getattr(request.user, "telegram_id", None)
                or getattr(request.user, "tg_user_id", None)
                or getattr(request.user, "tg_id", None)
            )

        # 1) создаём intent, в нём уже зафиксирован проект и инициатор
        intent = ChatLinkIntent.create_for(
            project=self.project,
            user=request.user,
            ttl_minutes=ttl,
            tg_user_id=tg_user_id,
        )

        # 2) вернём данные для фронта; ссылка /start может не использоваться, но оставим для совместимости
        start_link = f"https://t.me/{BOT_USERNAME}?start={intent.token}" if BOT_USERNAME else ""
        out = ChatLinkIntentResponseSerializer({
            "token": intent.token,
            "start_link": start_link,
            "expires_at": intent.expires_at,
        })
        return Response(out.data, status=status.HTTP_201_CREATED)
