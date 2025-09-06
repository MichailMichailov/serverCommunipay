import json
from rest_framework import decorators, response, status, permissions

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, response
from apiCommuniPay.projects.models import Project
from .models import TelegramChat, ChatLinkIntent
from .serializers import TelegramChatSerializer, ChatLinkIntentCreateSerializer, ChatLinkIntentResponseSerializer
from .permissions import IsProjectOwner
import threading
from apiCommuniPay.sse.views import send_message_to_token
BOT_USERNAME = getattr(settings, "TELEGRAM_BOT_USERNAME", "")

@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.AllowAny])
def healthz(_request):
    return response.Response(status=status.HTTP_204_NO_CONTENT)


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
        # 1) создаём intent, в нём уже зафиксирован проект и инициатор
        intent = ChatLinkIntent.create_for(self.project, request.user, ttl_minutes=ttl)

        # 2) постараемся зафиксировать telegram user id того, кто начал привязку
        #    a) из запроса (если фронт прислал)
        #    b) из атрибутов пользователя (если у нас сохранён tg id после login)
        tg_user_id = (
            serializer.validated_data.get("tg_user_id")
            if hasattr(serializer, "validated_data") else None
        )
        
        if tg_user_id is None:
            tg_user_id = (
                getattr(request.user, "tg_user_id", None)
                or getattr(request.user, "telegram_id", None)
                or getattr(request.user, "tg_id", None)
            )
        if tg_user_id:
            if intent.tg_user_id != tg_user_id:
                intent.tg_user_id = tg_user_id
                intent.save(update_fields=["tg_user_id"])
        # 3) вернём данные для фронта; ссылка /start может не использоваться, но оставим для совместимости
        start_link = f"https://t.me/{BOT_USERNAME}?start={intent.token}" if BOT_USERNAME else ""
        out = ChatLinkIntentResponseSerializer({
            "token": intent.token,
            "start_link": start_link,
            "expires_at": intent.expires_at,
        })
        # это только пример как слать 
        # send_message_to_token(token, json.dumps({"message": message}))
        # с начала шлю токен ретурном
        # потом чере 5 секун сообщение для теста 
        threading.Timer(5, send_delayed_message, 
        args=(intent.token, "Hello after 5 seconds")).start()

        return response.Response(out.data, status=201)
def send_delayed_message(token, message):
    """
    Отправка сообщения через SSE клиенту с токеном token
    """
    # message должен быть сериализован в JSON
    send_message_to_token(token, json.dumps({"message": message}))
