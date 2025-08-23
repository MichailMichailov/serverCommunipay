from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apiCommuniPay.accounts"
    def ready(self):
        # если добавишь signals.py — будет подключено автоматически
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
