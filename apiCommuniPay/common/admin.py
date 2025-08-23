# apiCommuniPay/common/admin.py
from django.contrib import admin
from .models import ChatLinkIntent, TelegramChat

@admin.register(TelegramChat)
class TelegramChatAdmin(admin.ModelAdmin):
    list_display = ("tg_id", "type", "title", "username", "project", "status", "created_at")
    list_filter = ("type", "status", "project")
    search_fields = ("tg_id", "title", "username")


@admin.register(ChatLinkIntent)
class ChatLinkIntentAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "initiator", "token", "tg_user_id", "tg_request_id", "chat_id", "status", "expires_at", "created_at")
    list_filter = ("status", "project")
    search_fields = ("token",)

