from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Project, ProjectMember


@receiver(post_save, sender=Project)
def ensure_owner_membership(sender, instance: Project, created, **kwargs):
    """
    После создания проекта гарантируем, что владелец записан в участники с ролью owner.
    Повторные вызовы — идемпотентны.
    """
    if not created:
        return
    ProjectMember.objects.get_or_create(
        project=instance,
        user=instance.owner,
        defaults={"role": ProjectMember.Role.OWNER},
    )
