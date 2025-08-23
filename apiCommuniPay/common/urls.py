from django.urls import path
from .views import ProjectChannelsList, CreateLinkIntent
from .webhook import telegram_webhook_view

app_name = "common"

urlpatterns = [
    path("projects/<uuid:project_id>/channels/", ProjectChannelsList.as_view()),
    path("projects/<uuid:project_id>/link-intents/", CreateLinkIntent.as_view()),
    path("telegram/webhook/<str:secret>/", telegram_webhook_view, name="telegram_webhook"),
]
