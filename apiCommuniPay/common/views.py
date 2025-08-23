from rest_framework import decorators, response, status, permissions

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, response
from apiCommuniPay.projects.models import Project
from .models import TelegramChat, ChatLinkIntent
from .serializers import TelegramChatSerializer, ChatLinkIntentCreateSerializer, ChatLinkIntentResponseSerializer
from .permissions import IsProjectOwner

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
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        ttl = data.validated_data["ttl_minutes"]
        intent = ChatLinkIntent.create_for(self.project, request.user, ttl_minutes=ttl)
        start_link = f"https://t.me/{BOT_USERNAME}?start={intent.token}"
        out = ChatLinkIntentResponseSerializer({
            "token": intent.token,
            "start_link": start_link,
            "expires_at": intent.expires_at,
        })
        return response.Response(out.data, status=201)
