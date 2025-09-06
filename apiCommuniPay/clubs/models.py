"""
Доменные модели подсистемы подписок («clubs»).

Содержит:
- Plan: платный тариф внутри конкретного проекта.
- PlanChannel: таблица-связка между тарифом и Telegram-чатом того же проекта.
- Subscription: подписка пользователя на тариф (active/expired/canceled).
- JoinRequest: служебная сущность — запрос на добавление в чат/канал по тарифу.

Ключевые инварианты и правила:
- Тариф (Plan) всегда принадлежит ровно одному проекту.
- К тарифу можно привязывать только те TelegramChat, которые принадлежат тому же проекту
  (валидируется в PlanChannel.clean).
- Цена неотрицательна (DB CheckConstraint `plan_price_non_negative`).
- Subscription хранит ключевые временные метки и компактный статус (active/expired/canceled).
- JoinRequest помогает координировать оплату и допуск в чат.

Типичный сценарий:
1) Владелец проекта создаёт тариф (Plan).
2) Тариф связывается с одним или несколькими Telegram-чатами/каналами (PlanChannel).
3) Пользователь оформляет и оплачивает подписку на тариф (Subscription).
4) Система создаёт JoinRequest и, после подтверждения, добавляет пользователя в целевой(ые) чат(ы).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apiCommuniPay.projects.models import Project
from apiCommuniPay.common.models import TelegramChat

User = settings.AUTH_USER_MODEL


class Plan(models.Model):
    """
    Платный тариф внутри проекта.

    Поля
    ----
    project : Project
        Проект-владелец тарифа.
    name : str
        Короткое человекочитаемое имя.
    description : str
        Необязательное подробное описание.
    limit : int | None
        Необязательный «жёсткий» лимит активных подписчиков.
    price : Decimal
        Неотрицательная цена тарифа; дополнительно защищена CheckConstraint в БД.
    is_public : bool
        Флаг публичной видимости тарифа.
    channels : M2M[TelegramChat]
        Привязанные чаты/каналы через промежуточную модель `PlanChannel`.

    Примечания
    ----------
    * Привязать можно только чаты того же проекта (валидируется в `PlanChannel.clean`).
    * Сортировка по умолчанию: `created_at` (DESC), затем `id`.
    """

    project = models.ForeignKey(Project, related_name="plans", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    limit = models.PositiveIntegerField(null=True, blank=True, help_text="Максимум подписчиков в тарифе")
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_public = models.BooleanField(default=True, db_index=True)

    channels = models.ManyToManyField(
        TelegramChat, through="PlanChannel", related_name="plans", blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        constraints = [
            models.CheckConstraint(check=Q(price__gte=0), name="plan_price_non_negative"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.project_id})"


class PlanChannel(models.Model):
    """
    Промежуточная таблица, связывающая тариф (Plan) с конкретным TelegramChat
    того же проекта.

    Целостность
    -----------
    * Пары (`plan`, `chat`) уникальны.
    * В `clean()` запрещаем связывать тариф и чат из разных проектов.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_channels")
    chat = models.ForeignKey(TelegramChat, on_delete=models.CASCADE, related_name="chat_plans")

    class Meta:
        unique_together = [("plan", "chat")]

    def clean(self):
        # Защитимся от привязки чата к плану другого проекта
        if self.plan.project_id != self.chat.project_id:
            raise ValidationError("План и чат должны принадлежать одному проекту.")

    def __str__(self) -> str:  # pragma: no cover
        return f"PlanChannel(plan={self.plan_id}, chat={self.chat_id})"


class Subscription(models.Model):
    """
    Подписка пользователя на конкретный тариф (Plan).

    Поля
    ----
    user : User
        Подписчик (FK на AUTH_USER_MODEL).
    plan : Plan
        Тариф; удаление тарифа заблокировано, пока есть подписки (PROTECT).
    status : str
        Текущий статус жизненного цикла: `active`, `expired` или `canceled`.
    starts_at / ends_at : datetime
        Временные границы подписки. Метод `is_expired()` — удобная проверка.
    created_at / updated_at : datetime
        Аудит-метки.

    Индексы
    -------
    Индекс по `(user, status)` ускоряет типовые выборки активных подписок.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(
        max_length=16,
        default="active",
        help_text="active / expired / canceled",
    )

    starts_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def is_expired(self) -> bool:
        return bool(self.ends_at and self.ends_at < timezone.now())

    def __str__(self) -> str:  # pragma: no cover
        return f"Subscription(user={self.user_id}, plan={self.plan_id}, status={self.status})"


class JoinRequest(models.Model):
    """
    Служебная сущность: запрос на добавление пользователя в конкретный чат/канал по тарифу.

    Используется в «рукопожатии» оплата → допуск. После подтверждения оплаты (или ручного
    одобрения админом) запрос переводится в `confirmed`, и пользователя добавляют в чат.

    Поля
    ----
    user : User
        Кто запрашивает/получает доступ.
    chat : TelegramChat
        Целевой чат/канал.
    plan : Plan
        Тариф, который даёт доступ к чату.
    status : str
        `pending` / `confirmed` / `rejected`.
    created_at / confirmed_at : datetime
        Метки времени для отслеживания жизненного цикла.

    Индексы
    -------
    Индексы по `(user, status)` и `(chat, status)` помогают в админке/дашбордах и автоматизациях.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    chat = models.ForeignKey(TelegramChat, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)

    status = models.CharField(
        max_length=16,
        choices=[
            ("pending", "Ожидает оплату"),
            ("confirmed", "Подтверждено"),
            ("rejected", "Отклонено"),
        ],
        default="pending",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["chat", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"JoinRequest(user={self.user_id}, chat={self.chat_id}, plan={self.plan_id}, status={self.status})"
