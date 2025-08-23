# apiCommuniPay/api/views_telegram.py
import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from apiCommuniPay.common.models import TelegramChat
from apiCommuniPay.accounts.models import User  # твоя модель пользователя

@csrf_exempt
def telegram_webhook(request, token: str):
    # простой guard по секрету
    if token != getattr(settings, "TELEGRAM_WEBHOOK_SECRET", ""):
        return HttpResponse(status=403)

    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        update = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    mcm = update.get("my_chat_member")
    if not mcm:
        # нам важны только события добавления/удаления бота
        return JsonResponse({"ok": True})

    chat = mcm.get("chat", {})
    actor = mcm.get("from", {})  # кто совершил действие (обычно админ)
    old = mcm.get("old_chat_member", {}).get("status")
    new = mcm.get("new_chat_member", {}).get("status")

    # интересует «бот появился/стал админом»
    became_member = old in ("left", "kicked") and new in ("member", "administrator")
    became_admin = new == "administrator"
    if not (became_member or became_admin):
        return JsonResponse({"ok": True})

    tg_chat_id = chat.get("id")
    title = chat.get("title") or ""
    chat_type = chat.get("type")  # group | supergroup | channel

    # кто добавил
    adder_tg_id = actor.get("id")
    user = None
    if adder_tg_id:
        # найди пользователя по telegram_id (адаптируй под свою схему)
        user = User.objects.filter(telegram_id=adder_tg_id).first()

    obj, _ = TelegramChat.objects.update_or_create(
        tg_chat_id=tg_chat_id,
        defaults=dict(
            title=title,
            type=chat_type,
            verified_at=timezone.now(),
            created_by=user if user else None,
        ),
    )

    # попытаться привязать к проекту: если у пользователя один проект или есть active_project
    project = None
    if user and hasattr(user, "active_project") and user.active_project_id:
        project = user.active_project
    elif user and hasattr(user, "project_set"):
        qs = user.project_set.all()
        project = qs.get() if qs.count() == 1 else None

    if project and obj.project_id != project.id:
        obj.project = project
        obj.save(update_fields=["project"])

    return JsonResponse({"ok": True})
