from django.db import models
# apiCommuniPay/common/models.py
from django.db import models
from django.conf import settings
import secrets, string, datetime as dt
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


def _short_token(n=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

class ChatLinkIntent(models.Model):
    """
    Намерение привязать чат к проекту через deeplink.
    Живёт короткое время. Склеивает:
      - проект
      - кто инициировал (user)
      - какой телеграм-пользователь нажал /start
      - request_id (для chat_shared)
      - чат, который в итоге привязали
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        CONSUMED = "consumed", "Использовано"
        EXPIRED = "expired", "Просрочено"
        CANCELLED = "cancelled", "Отменено"

    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="link_intents")
    initiator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="link_intents")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    tg_user_id = models.BigIntegerField(null=True, blank=True)        # кто нажал /start
    tg_request_id = models.BigIntegerField(null=True, blank=True)     # request_id для chat_shared
    chat_id = models.BigIntegerField(null=True, blank=True)           # итоговый chat.id
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def create_for(cls, project, user, ttl_minutes: int = 15):
        token = f"proj_{_short_token(16)}"
        return cls.objects.create(
            project=project,
            initiator=user,
            token=token,
            expires_at=timezone.now() + dt.timedelta(minutes=ttl_minutes),
        )

    def is_active(self):
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()

    def mark_consumed(self, chat_id: int):
        self.chat_id = chat_id
        self.status = self.Status.CONSUMED
        self.consumed_at = timezone.now()
        self.save(update_fields=["chat_id", "status", "consumed_at"])


class TelegramChat(models.Model):
    class ChatType(models.TextChoices):
        CHANNEL = "channel", "Channel"
        SUPERGROUP = "supergroup", "Supergroup"
        GROUP = "group", "Group"
        PRIVATE = "private", "Private"

    class ChatStatus(models.TextChoices):
        ACTIVE = "active", "Активен"
        PENDING_RIGHTS = "pending_rights", "Требуются права"
        INACTIVE = "inactive", "Неактивен"

    id = models.BigAutoField(primary_key=True)
    tg_id = models.BigIntegerField(unique=True, db_index=True)
    type = models.CharField(max_length=32, choices=ChatType.choices)
    title = models.CharField(max_length=256, blank=True, default="")
    username = models.CharField(max_length=256, blank=True, default="")
    project = models.ForeignKey("projects.Project", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="telegram_chats")
    status = models.CharField(max_length=32, choices=ChatStatus.choices, default=ChatStatus.PENDING_RIGHTS)
    added_by = models.BigIntegerField(null=True, blank=True)  # tg user id, кто привязал
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type}:{self.tg_id} {self.title or self.username}"

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class OwnedModel(models.Model):
    """
    Ожидает поле owner = FK(User). Не абстрактная проверка — но класс сам абстрактный.
    """
    class Meta:
        abstract = True
