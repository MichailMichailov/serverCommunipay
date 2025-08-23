import uuid
from django.conf import settings
from django.db import models
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class Project(models.Model):
    """
    Проект — «рабочая среда» для клубов, акций, каналов и т.д.
    Сейчас содержит базовые поля. Дальше в смежных приложениях
    можно добавить ForeignKey(Project) к нужным моделям.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="owned_projects",
        help_text="Владелец проекта (имеет полные права)."
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["owner", "name"]),
        ]
        constraints = [
            # Опционально: у владельца не должно быть двух проектов с одинаковым названием
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_owner_project_name"),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    def save(self, *args, **kwargs):
        # автогенерация slug при первом сохранении или если пустой
        if not self.slug:
            base = slugify(self.name) or "project"
            slug = base
            i = 2
            while Project.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class ProjectMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        EDITOR = "editor", "Editor"
        VIEWER = "viewer", "Viewer"

    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")
        indexes = [
            models.Index(fields=["project", "user"]),
            models.Index(fields=["project", "role"]),
        ]

    def __str__(self):
        return f"{self.user} @ {self.project} ({self.role})"
