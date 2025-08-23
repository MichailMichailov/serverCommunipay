from django.urls import path
from .views import index, RegisterView, MeView, PasswordChangeView, LogoutView, TelegramAuthView
from .auth_views import RegisterView
from .views_telegram import telegram_webhook

urlpatterns = [
    path("", index, name="api-index"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/telegram/", TelegramAuthView.as_view(), name="telegram-auth"),
    path("api/tg/webhook/<str:token>/", telegram_webhook),
]
