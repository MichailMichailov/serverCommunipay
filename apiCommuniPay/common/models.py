import datetime as dt
import secrets
import string

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.db.models import Q, UniqueConstraint


def _short_token(n: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


class ChatLinkIntent(models.Model):
    """
    Интент (одноразовое намерение) привязать Telegram-чат к проекту.

    Поток в двух словах:
    1) Пользователь жмёт «Добавить канал/чат» → создаём интент (status=pending) и токен.
    2) Юзер открывает бота: `/start <token>` → сохраняем tg_user_id у интента.
    3) Из мини-аппы «поделиться чатом» → приходят chat_id и request_id → связываем с интентом.
    4) Боту выдают права админа в чате → по my_chat_member → чат становится ACTIVE, интент consumed.

    Главное про поля:
    - project: к какому проекту подвязываем чат
    - initiator: кто начал процесс в нашем сервисе (Django User)
    - token: одноразовый код для /start
    - tg_user_id: кто нажал /start в Telegram
    - tg_request_id: request_id из chat_shared
    - chat_id: выбранный чат (как только известен)
    - status: pending | consumed | expired | cancelled
    - expires_at: дедлайн действия токена
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        CONSUMED = "consumed", "Использовано"
        EXPIRED = "expired", "Просрочено"
        CANCELLED = "cancelled", "Отменено"

    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="link_intents",
    )
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="link_intents",
    )
    token = models.CharField(max_length=64, unique=True)
    tg_user_id = models.PositiveBigIntegerField(
        null=True, blank=True, db_index=True, validators=[MinValueValidator(1)]
    )       # кто нажал /start
    tg_request_id = models.PositiveBigIntegerField(
        null=True, blank=True, db_index=True, validators=[MinValueValidator(1)]
    )    # request_id для chat_shared
    chat_id = models.BigIntegerField(
        null=True, blank=True, db_index=True, validators=[MinValueValidator(1)]
    )          # итоговый chat.id
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "намерение привязки чата"
        verbose_name_plural = "намерения привязки чатов"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="intent_status_exp"),
            models.Index(fields=["tg_user_id", "status", "expires_at"], name="intent_user_status_exp"),
            models.Index(fields=["tg_request_id", "status", "expires_at"], name="intent_req_status_exp"),
        ]
        constraints = [
            UniqueConstraint(
                fields=["project", "initiator"],
                condition=Q(status="pending"),
                name="one_pending_intent_per_user_and_project",
            ),
            # Если статус consumed, то consumed_at не NULL
            models.CheckConstraint(
                name="intent_consumed_has_ts",
                check=(
                    models.Q(status="consumed", consumed_at__isnull=False)
                    | ~models.Q(status="consumed")
                ),
            ),
            # Если есть consumed_at, то статус обязательно consumed
            models.CheckConstraint(
                name="intent_ts_means_consumed",
                check=(models.Q(consumed_at__isnull=True) | models.Q(status="consumed")),
            ),
        ]

    # внутри класса ChatLinkIntent (замените целиком метод create_for)

    @classmethod
    def create_for(
            cls,
            project,
            user,
            ttl_minutes: int = 15,
            tg_user_id: int | None = None,
    ):
        """
        Гарантирует не более одного pending-интента на (project, initiator).
        При повторном нажатии «добавить чат/канал» возвращает уже существующий,
        продлевая срок действия и подставляя tg_user_id, если он появился.
        Корректно обрабатывает гонки по уникальному ограничению.
        """
        now = timezone.now()
        expires = now + dt.timedelta(minutes=ttl_minutes)

        with transaction.atomic():
            # 1) Пытаемся переиспользовать актуальный pending
            existing = (
                cls.objects
                .select_for_update()
                .filter(project=project, initiator=user, status=cls.Status.PENDING)
                .order_by("-created_at")
                .first()
            )
            if existing:
                fields = []
                if tg_user_id and not existing.tg_user_id:
                    existing.tg_user_id = tg_user_id
                    fields.append("tg_user_id")
                if existing.expires_at < expires:
                    existing.expires_at = expires
                    fields.append("expires_at")
                if fields:
                    existing.save(update_fields=fields)
                return existing

            # 2) Pending ещё нет — создаём новый с уникальным token
            for _ in range(8):  # достаточно, коллизии почти нереальны
                token = f"proj_{_short_token(16)}"
                try:
                    return cls.objects.create(
                        project=project,
                        initiator=user,
                        token=token,
                        tg_user_id=tg_user_id,
                        expires_at=expires,
                    )
                except IntegrityError as e:
                    msg = str(e)
                    # (a) конфликт токена — пробуем сгенерить другой
                    if "token" in msg:
                        continue
                    # (b) гонка по уникальному индексу one_pending_intent_per_user_and_project — вернём существующий
                    if "one_pending_intent_per_user_and_project" in msg:
                        return (
                            cls.objects
                            .filter(project=project, initiator=user, status=cls.Status.PENDING)
                            .order_by("-created_at")
                            .first()
                        )
                    # (c) прочее — пробрасываем
                    raise

        raise RuntimeError("Failed to generate unique token for ChatLinkIntent")

    def is_active(self) -> bool:
        """True, если интент ещё действителен: status=pending и expires_at в будущем."""
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()

    def mark_consumed(self, chat_id: int):
        """Помечает интент как использованный: сохраняет chat_id, status=consumed и consumed_at."""
        now = timezone.now()
        updated = (
            ChatLinkIntent.objects
            .filter(pk=self.pk, status=self.Status.PENDING)
            .update(chat_id=chat_id, status=self.Status.CONSUMED, consumed_at=now)
        )
        if updated:
            # синхронизируем локальный инстанс на всякий
            self.chat_id = chat_id
            self.status = self.Status.CONSUMED
            self.consumed_at = now

    def __str__(self) -> str:
        return f"Intent({self.token}) → project={self.project_id} status={self.status}"


class TelegramChat(models.Model):
    """
    Подключённый Telegram-чат/канал, связанный (или ещё связываемый) с проектом.

    Что храним:
    - tg_id: числовой ID чата (уникален)
    - type: 'channel' | 'supergroup' | 'group' | 'private'
    - title/username: человекочитаемые подписи
    - project: проект, к которому привязан чат (может быть NULL до выдачи прав)
    - status:
        • pending_rights — нашли чат через chat_shared, но прав у бота ещё нет
        • active          — бот админ, интеграция рабочая
        • inactive        — бота удалили/понизили
    - can_invite_users: у бота есть право приглашать/одобрять заявки
    - join_by_request: в чате включён режим вступления по заявке
    - added_by: Telegram-ID пользователя, который дал боту права
    - last_synced_at: когда последний раз сверяли права/настройки

    Жизненный цикл:
    1) chat_shared → создаём/обновляем запись как PENDING_RIGHTS.
    2) my_chat_member(administrator) → переводим в ACTIVE, (если был интент) — линкуем проект.
    3) left/kicked/restricted/member → переводим в INACTIVE.
    """
    class ChatType(models.TextChoices):
        """Типы Telegram-чатов, которые поддерживаем."""

        CHANNEL = "channel", "Channel"
        SUPERGROUP = "supergroup", "Supergroup"
        GROUP = "group", "Group"
        PRIVATE = "private", "Private"

    class ChatStatus(models.TextChoices):
        """Состояние подключения чата в нашей системе."""

        ACTIVE = "active", "Активен"
        PENDING_RIGHTS = "pending_rights", "Требуются права"
        INACTIVE = "inactive", "Неактивен"

    id = models.BigAutoField(primary_key=True)
    tg_id = models.BigIntegerField(
        null=False,
        blank=False,
        unique=True,
    )
    type = models.CharField(max_length=32, choices=ChatType.choices)
    title = models.CharField(max_length=256, blank=True, default="")
    username = models.CharField(max_length=256, blank=True, default="")
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="telegram_chats",
    )
    status = models.CharField(
        max_length=32,
        choices=ChatStatus.choices,
        default=ChatStatus.PENDING_RIGHTS,
        db_index=True,
    )
    added_by = models.PositiveBigIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])  # tg user id, кто привязал
    created_at = models.DateTimeField(auto_now_add=True)

    # capability flags, синхронизируем из вебхука when possible
    can_invite_users = models.BooleanField(default=False)  # у бота есть право приглашать/одобрять заявки
    join_by_request = models.BooleanField(default=False)   # в чате включены заявки на вступление
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "телеграм-чат"
        verbose_name_plural = "телеграм-чаты"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"], name="tgchat_project_status"),
        ]

    def __str__(self) -> str:
        return f"{self.type}:{self.tg_id} {self.title or self.username}"


class TimeStampedModel(models.Model):
    """
    Абстрактная база: два стандартных поля аудита — created_at и updated_at.
    Подмешивайте в модели, где нужен единый учёт времени создания/обновления.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(models.Model):
    """
    Абстрактная база для моделей с владельцем.
    Предполагает наличие поля `owner = FK(User)` в наследнике и упрощает проверки доступа.
    """

    class Meta:
        abstract = True
