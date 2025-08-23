from rest_framework import serializers
from .models import TelegramChat, ChatLinkIntent

class TelegramChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramChat
        fields = ("tg_id", "type", "title", "username", "status")

class ChatLinkIntentCreateSerializer(serializers.Serializer):
    ttl_minutes = serializers.IntegerField(required=False, min_value=1, max_value=60, default=15)

class ChatLinkIntentResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    start_link = serializers.CharField()
    expires_at = serializers.DateTimeField()
