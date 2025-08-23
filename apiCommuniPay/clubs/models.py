from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from apiCommuniPay.projects.models import Project
from apiCommuniPay.common.models import TelegramChat

User = settings.AUTH_USER_MODEL

class Club(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_clubs")
    managers = models.ManyToManyField(User, blank=True, related_name="managed_clubs")
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

class Plan(models.Model):
    project = models.ForeignKey(Project, related_name="plans", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # 👇 добавляем обратно флаг публичности для списка планов (совместимость с тестами)
    is_public = models.BooleanField(default=True, db_index=True)

    # ваша текущая связка с каналами остаётся
    channels = models.ManyToManyField(
        TelegramChat, through="PlanChannel", related_name="plans", blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.project_id})"

class PlanChannel(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='plan_channels')
    chat = models.ForeignKey(TelegramChat, on_delete=models.CASCADE, related_name='chat_plans')

    class Meta:
        unique_together = [('plan', 'chat')]

    def clean(self):
        # защитимся от привязки чата к плану другого проекта
        if self.plan.project_id != self.chat.project_id:
            raise ValidationError("План и чат должны принадлежать одному проекту.")

# если у вас уже есть Subscription, убедитесь, что она ссылается на Plan
class Subscription(models.Model):
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=16, default='active')  # active / expired / canceled
    starts_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),
        ]

