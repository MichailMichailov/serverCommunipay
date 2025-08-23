from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apiCommuniPay.projects'

    def ready(self):
        from . import signals  # noqa
