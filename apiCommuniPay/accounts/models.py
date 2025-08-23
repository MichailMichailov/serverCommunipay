from django.contrib.auth.models import AbstractUser
from django.db import models

class Roles(models.TextChoices):
    SUPERADMIN = "superadmin", "Super Admin"
    ADMIN      = "admin", "Admin"
    OWNER      = "owner", "Club Owner"
    MANAGER    = "manager", "Club Manager"
    MEMBER     = "member", "Member"

class User(AbstractUser):
    role = models.CharField(max_length=16, choices=Roles.choices, default=Roles.MEMBER, db_index=True)

    # Telegram identity
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True, db_index=True)
    tg_username = models.CharField(max_length=64, null=True, blank=True)
    tg_first_name = models.CharField(max_length=64, null=True, blank=True)
    tg_last_name = models.CharField(max_length=64, null=True, blank=True)
    tg_language_code = models.CharField(max_length=8, null=True, blank=True)
    tg_photo_url = models.URLField(null=True, blank=True)

    @property
    def is_platform_staff(self) -> bool:
        return self.role in {Roles.SUPERADMIN, Roles.ADMIN} or self.is_staff
