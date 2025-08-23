# apiCommuniPay/common/webhook.py
import random, json, logging
import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import ChatLinkIntent, TelegramChat

log = logging.getLogger(__name__)

BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_SECRET = settings.TELEGRAM_WEBHOOK_SECRET  # рандомная строка в env

def tg_api(method: str, **params):
    r = requests.post(f"{BOT_API}/{method}", json=params, timeout=10)
    try:
        data = r.json()
    except Exception:
        log.exception("Telegram response is not JSON: %s", r.text[:2000])
        raise
    if not data.get("ok"):
        log.error("Telegram API error: %s", data)
    return data

def _reply_markup_with_request_chat(request_id: int):
    # KeyboardButton with request_chat (работает в приватном чате с ботом)
    return {
        "keyboard": [[{
            "text": "Выбрать чат/канал",
            "request_chat": {
                "request_id": request_id,
                "chat_is_channel": True,           # можно выбрать канал
                "chat_is_forum": False,
                "bot_administrator_rights": {      # какие права хотим в супергруппе
                    "can_manage_chat": True,
                    "can_delete_messages": True,
                    "can_invite_users": True,
                    "can_restrict_members": True,
                    "can_pin_messages": True,
                    "can_manage_topics": True
                },
                "bot_is_member": True              # бот должен быть участником (для групп)
            }
        }]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "is_persistent": False
    }

def _upsert_chat(chat_id: int, meta: dict, project=None, added_by=None, status=None):
    tc, _ = TelegramChat.objects.get_or_create(tg_id=chat_id, defaults={
        "type": meta.get("type", "channel"),
        "title": meta.get("title") or "",
        "username": meta.get("username") or "",
        "project": project,
        "added_by": added_by or None,
    })
    changed = False
    for fld, val in (
        ("type", meta.get("type") or tc.type),
        ("title", meta.get("title") or tc.title),
        ("username", meta.get("username") or tc.username),
    ):
        if getattr(tc, fld) != val:
            setattr(tc, fld, val)
            changed = True
    if project and tc.project_id != project.id:
        tc.project = project
        changed = True
    if added_by and tc.added_by != added_by:
        tc.added_by = added_by
        changed = True
    if status and tc.status != status:
        tc.status = status
        changed = True
    if changed:
        tc.save()
    return tc

@csrf_exempt
def telegram_webhook_view(request, secret: str):
    if secret != WEBHOOK_SECRET:
        return HttpResponse(status=403)

    try:
        update = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    # 1) /start proj_xxx
    msg = update.get("message")
    if msg and "text" in msg:
        text: str = msg["text"]
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            payload = parts[1] if len(parts) > 1 else ""
            chat_id = msg["chat"]["id"]
            from_id = msg["from"]["id"]

            if payload.startswith("proj_"):
                # находим активное намерение
                intent = ChatLinkIntent.objects.filter(token=payload, status=ChatLinkIntent.Status.PENDING).first()
                if not intent or not intent.is_active():
                    tg_api("sendMessage", chat_id=chat_id, text="Ссылка устарела. Повторите подключение из мини-аппа.")
                    return JsonResponse({"ok": True})

                # помечаем кто нажал start
                if intent.tg_user_id != from_id:
                    intent.tg_user_id = from_id

                # создаём request_id для chat_shared
                if not intent.tg_request_id:
                    intent.tg_request_id = random.randint(10_000, 2_000_000_000)
                intent.save(update_fields=["tg_user_id", "tg_request_id"])

                tg_api("sendMessage",
                      chat_id=chat_id,
                      text="Теперь выберите канал/чат и добавьте меня админом.\n"
                           "Либо вручную: откройте нужный канал → Администраторы → добавить бота.",
                      reply_markup=_reply_markup_with_request_chat(intent.tg_request_id))
                return JsonResponse({"ok": True})

    # 2) chat_shared (после нажатия «Выбрать чат/канал»)
    if msg and "chat_shared" in msg:
        shared = msg["chat_shared"]
        req_id = shared.get("request_id")
        shared_chat_id = shared.get("chat_id")
        from_id = msg["from"]["id"]

        intent = ChatLinkIntent.objects.filter(tg_request_id=req_id, status=ChatLinkIntent.Status.PENDING).first()
        if not intent or not intent.is_active():
            return JsonResponse({"ok": True})

        # предварительно создаём запись чата со статусом "требуются права"
        meta = {}
        _upsert_chat(shared_chat_id, meta, project=None, added_by=from_id, status=TelegramChat.ChatStatus.PENDING_RIGHTS)

        # просим дать права и добавить бота админом
        tg_api("sendMessage", chat_id=msg["chat"]["id"],
               text="Почти готово! Добавьте бота админом в выбранный канал/чат.\n"
                    "Как только бот станет админом, канал привяжется к проекту.")

        # запомним chat_id в намерении (финализируем при my_chat_member)
        intent.chat_id = shared_chat_id
        intent.save(update_fields=["chat_id"])
        return JsonResponse({"ok": True})

    # 3) my_chat_member (бот стал админом в каком-то чате)
    mcm = update.get("my_chat_member")
    if mcm:
        chat = mcm.get("chat") or {}
        new = mcm.get("new_chat_member") or {}
        actor = mcm.get("from") or {}
        status = new.get("status")
        bot_user = new.get("user") or {}
        if status == "administrator" and bot_user.get("is_bot"):
            chat_id = chat.get("id")
            actor_id = actor.get("id")  # кто добавил
            # найдём ближайшее активное намерение этого человека
            intent = (ChatLinkIntent.objects
                      .filter(status=ChatLinkIntent.Status.PENDING,
                              tg_user_id=actor_id,
                              expires_at__gt=timezone.now())
                      .order_by("-created_at")
                      .first())
            # получим метаинфо о чате (best-effort)
            meta = {"type": chat.get("type"), "title": chat.get("title"), "username": chat.get("username")}

            if intent:
                tc = _upsert_chat(chat_id, meta, project=intent.project, added_by=actor_id, status=TelegramChat.ChatStatus.ACTIVE)
                intent.mark_consumed(chat_id=chat_id)
                # уведомим в ЛС
                tg_api("sendMessage", chat_id=actor_id,
                       text=f"Канал/чат '{tc.title or tc.username or tc.tg_id}' привязан к проекту «{intent.project.name}». "
                            f"Откройте мини-апп, чтобы управлять.")
            else:
                # нет намерения — просто сохраним как найденный (без проекта)
                _upsert_chat(chat_id, meta, project=None, added_by=actor_id, status=TelegramChat.ChatStatus.ACTIVE)

        return JsonResponse({"ok": True})

    return JsonResponse({"ok": True})
