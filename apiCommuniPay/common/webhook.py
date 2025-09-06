# apiCommuniPay/common/webhook.py
import json
import logging

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apiCommuniPay.sse.views import send_message_to_token

from .models import ChatLinkIntent, TelegramChat

_TELEGRAM_BOT_ID = getattr(settings, "TELEGRAM_BOT_ID", None)
TELEGRAM_BOT_ID = int(_TELEGRAM_BOT_ID) if _TELEGRAM_BOT_ID not in (None, "") else None

WEBHOOK_SECRET  = getattr(settings, "TELEGRAM_WEBHOOK_SECRET")
BOT_TOKEN       = getattr(settings, "TELEGRAM_BOT_TOKEN", None)

TG_API = "https://api.telegram.org"

logger = logging.getLogger("tg.webhook")

def _ok():
    return JsonResponse({"ok": True})

def _tg_api(method: str, **params):
    """Мини-обёртка над Telegram Bot API (используем только для getChat)."""
    if not BOT_TOKEN:
        logger.debug("_tg_api(%s): skipped, no BOT_TOKEN", method)
        return {}
    url = f"{TG_API}/bot{BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, json=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            logger.debug("_tg_api(%s) ok: %s", method, {k: v for k, v in params.items() if k != 'chat_id'})
            return data.get("result", {})
        logger.warning("_tg_api(%s) not ok: %s", method, data)
        return {}
    except Exception as e:
        logger.exception("_tg_api(%s) failed: %s", method, e)
        return {}

def _get_chat_flags(chat_id: int) -> dict:
    """
    Возвращает {'join_by_request': bool} по данным getChat.
    Если токена нет или ошибка — считаем False.
    """
    try:
        info = _tg_api("getChat", chat_id=chat_id) or {}
        logger.debug("get_chat_flags: chat_id=%s -> %s", chat_id, info)
        return {"join_by_request": bool(info.get("join_by_request", False))}
    except Exception:
        logger.warning("get_chat_flags: chat_id=%s -> failed, defaulting join_by_request=False", chat_id)
        return {"join_by_request": False}

@csrf_exempt
@require_POST
def telegram_webhook_view(request, secret: str):
    # 1) защита секретом в path (+ опционально заголовок от Telegram)
    if secret != WEBHOOK_SECRET:
        logger.warning("webhook: bad secret in path")
        return HttpResponseForbidden("bad secret in path")
    hdr_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if hdr_secret and hdr_secret != WEBHOOK_SECRET:
        logger.warning("webhook: bad secret header")
        return HttpResponseForbidden("bad secret header")

    try:
        update = json.loads(request.body.decode("utf-8"))
    except Exception:
        return _ok()

    logger.debug("webhook: received update keys=%s", list((update or {}).keys()) if 'update' in locals() else None)

    if (m := update.get("my_chat_member")):
        return _handle_my_chat_member(m)
    if (msg := update.get("message")):
        return _handle_message(msg)

    return _ok()


# ---------- message handlers ----------

def _handle_message(msg: dict):
    """ /start <token>, chat_shared """
    from_user = (msg.get("from") or {})
    from_id   = from_user.get("id")

    logger.info("message: from_id=%s keys=%s", from_id, list(msg.keys()))

    # a) /start <token>
    text = msg.get("text") or ""
    if text.startswith("/start "):
        token = text.split(" ", 1)[1].strip()
        logger.info("message: /start token=%s from_id=%s", token, from_id)
        _touch_start_token(token, from_id)
        return _ok()

    # b) chat_shared (пользователь «поделился чатом» из Telegram)
    if "chat_shared" in msg:
        cs = msg["chat_shared"]
        try:
            chat_id = int(cs.get("chat_id"))
        except (TypeError, ValueError):
            chat_id = None
        req_id = cs.get("request_id")
        logger.info("message: chat_shared from_id=%s chat_id=%s request_id=%s", from_id, chat_id, req_id)
        _handle_chat_shared(from_id, req_id, chat_id)
        return _ok()

    return _ok()


def _touch_start_token(token: str, from_id: int | None):
    logger.debug("touch_start_token: token=%s from_id=%s", token, from_id)
    if not token or not from_id:
        return
    intent = (ChatLinkIntent.objects
              .filter(token=token, status=ChatLinkIntent.Status.PENDING,
                      expires_at__gt=timezone.now())
              .order_by("-created_at").first())
    if not intent:
        return
    logger.info("touch_start_token: matched intent id=%s project=%s initiator_id=%s", intent.id, getattr(intent.project, 'id', None), intent.initiator_id)
    # Запомним, кто нажал /start (для дальнейшего сопоставления)
    if intent.tg_user_id != from_id:
        logger.debug("touch_start_token: set tg_user_id=%s for intent id=%s", from_id, intent.id)
        intent.tg_user_id = from_id
        intent.save(update_fields=["tg_user_id"])


def _handle_chat_shared(from_id: int | None, req_id: int | None, chat_id: int | None):
    """Помечаем чат как «ожидает права», линкуем к проекту из активного intent этого пользователя"""
    if not (from_id and chat_id):
        logger.warning("chat_shared: missing from_id or chat_id: from_id=%s chat_id=%s", from_id, chat_id)
        return
    intent = (_find_active_intent_for_request(req_id) or _find_active_intent_for_user(from_id))
    source = 'request_id' if intent and intent.tg_request_id == req_id else ('user' if intent else 'none')
    logger.info("chat_shared: from_id=%s chat_id=%s request_id=%s intent_id=%s source=%s", from_id, chat_id, req_id, getattr(intent, 'id', None), source)

    chat_obj, created = TelegramChat.objects.update_or_create(
        tg_id=chat_id,
        defaults={
            "type": TelegramChat.ChatType.SUPERGROUP,   # обязательное поле в модели
            "title": "",
            "username": "",
            "project": intent.project if intent else None,
            "status": TelegramChat.ChatStatus.PENDING_RIGHTS,
            "added_by": from_id,
        },
    )
    logger.debug("chat_shared: chat upserted id=%s created=%s project=%s", chat_obj.id, created, getattr(chat_obj.project, 'id', None))

    if intent:
        fields = []
        if intent.tg_request_id != req_id:
            intent.tg_request_id = req_id
            fields.append("tg_request_id")
        if intent.chat_id != chat_id:
            intent.chat_id = chat_id
            fields.append("chat_id")
        if fields:
            intent.save(update_fields=fields)
            logger.debug("chat_shared: intent %s updated fields=%s", intent.id, fields)


# ---------- my_chat_member (когда бота сделали админом) ----------

def _handle_my_chat_member(mcm: dict):
    chat      = mcm.get("chat") or {}
    new_cm    = mcm.get("new_chat_member") or {}
    actor     = mcm.get("from") or {}
    bot_user  = (new_cm.get("user") or {})

    logger.info("my_chat_member: chat_id=%s type=%s new_status=%s actor_id=%s bot_id=%s", chat.get("id"), chat.get("type"), new_cm.get("status"), actor.get("id"), (new_cm.get("user") or {}).get("id"))

    # обрабатываем только событие про бота; если TELEGRAM_BOT_ID задан — сверяем
    if not bot_user.get("is_bot"):
        return _ok()
    if TELEGRAM_BOT_ID is not None and int(bot_user.get("id")) != TELEGRAM_BOT_ID:
        return _ok()

    new_status = new_cm.get("status")
    try:
        chat_id = int(chat["id"])
    except (KeyError, TypeError, ValueError):
        return _ok()
    chat_type  = chat.get("type")
    title      = chat.get("title") or chat.get("username") or str(chat_id)
    actor_id   = actor.get("id")

    # права админа бота: важно can_invite_users
    can_invite = bool(new_cm.get("can_invite_users", False))
    flags = _get_chat_flags(chat_id)
    join_by_request = bool(flags.get("join_by_request", False))

    logger.debug("my_chat_member: flags can_invite=%s join_by_request=%s", can_invite, join_by_request)

    # рассчёт статуса
    if new_status == "administrator":
        new_db_status = TelegramChat.ChatStatus.ACTIVE if can_invite else TelegramChat.ChatStatus.PENDING_RIGHTS
    elif new_status in ("member", "restricted"):
        new_db_status = TelegramChat.ChatStatus.PENDING_RIGHTS
    elif new_status in ("left", "kicked"):
        new_db_status = TelegramChat.ChatStatus.INACTIVE
    else:
        return _ok()

    logger.info("my_chat_member: mapped status -> %s", new_db_status)

    # upsert записи о чате + фиксация флагов
    chat_obj, created = TelegramChat.objects.update_or_create(
        tg_id=chat_id,
        defaults={
            "type": chat_type or TelegramChat.ChatType.SUPERGROUP,
            "title": title,
            "username": chat.get("username") or "",
            "status": new_db_status,
            "added_by": actor_id,
            "can_invite_users": can_invite,
            "join_by_request": join_by_request,
        },
    )
    logger.debug("my_chat_member: chat upserted id=%s created=%s", chat_obj.id, created)
    # отметим время синхронизации
    TelegramChat.objects.filter(pk=chat_obj.pk).update(last_synced_at=timezone.now())

    # если бот стал админом — попробуем привязать к проекту по intent
    if new_status == "administrator":
        _link_chat_to_project(
            chat_id=chat_id,
            chat_type=chat_type,
            title=title,
            actor_id=actor_id,
            status=new_db_status,
            can_invite_users=can_invite,
            join_by_request=join_by_request,
        )
    return _ok()



def _link_chat_to_project(
    chat_id: int,
    chat_type: str | None,
    title: str,
    actor_id: int | None,
    status: str,
    can_invite_users: bool,
    join_by_request: bool,
):
    logger.info("link_chat_to_project: chat_id=%s actor_id=%s", chat_id, actor_id)
    intent = (
        ChatLinkIntent.objects
        .filter(chat_id=chat_id, status=ChatLinkIntent.Status.PENDING, expires_at__gt=timezone.now())
        .order_by("-created_at").first()
    ) or _find_active_intent_for_user(actor_id)
    logger.info("link_chat_to_project: intent_by_chat_or_user=%s project=%s", getattr(intent, 'id', None), getattr(getattr(intent, 'project', None), 'id', None))

    defaults = {
        "title": title,
        "type": chat_type or TelegramChat.ChatType.SUPERGROUP,
        "added_by": actor_id,
        # не «активируем» тут, статус уже рассчитан выше:
        "status": status,
        "can_invite_users": can_invite_users,
        "join_by_request": join_by_request,
    }
    if intent:
        defaults["project"] = intent.project

    chat_obj, _ = TelegramChat.objects.update_or_create(tg_id=chat_id, defaults=defaults)
    logger.info("link_chat_to_project: chat saved pk=%s project=%s status=%s", chat_obj.pk, getattr(chat_obj.project, 'id', None), chat_obj.status)
    TelegramChat.objects.filter(pk=chat_obj.pk).update(last_synced_at=timezone.now())

    if intent:
        logger.info("link_chat_to_project: consuming intent id=%s for chat_id=%s", intent.id, chat_id)
        intent.mark_consumed(chat_id=chat_id)
        send_message_to_token(intent.token, json.dumps({"message": "любые поля любого сообщения"}))



# ---------- helpers ----------

def _find_active_intent_for_user(tg_user_id: int | None):
    if not tg_user_id:
        logger.debug("find_intent_by_user: key=%s -> intent_id=None", tg_user_id)
        return None
    intent = (ChatLinkIntent.objects
            .filter(tg_user_id=tg_user_id,
                    status=ChatLinkIntent.Status.PENDING,
                    expires_at__gt=timezone.now())
            .order_by("-created_at").first())
    logger.debug("find_intent_by_user: key=%s -> intent_id=%s", tg_user_id, getattr(intent, 'id', None))
    return intent


def _find_active_intent_for_request(req_id: int | None):
    if not req_id:
        logger.debug("find_intent_by_request: key=%s -> intent_id=None", req_id)
        return None
    intent = (ChatLinkIntent.objects
            .filter(tg_request_id=req_id,
                    status=ChatLinkIntent.Status.PENDING,
                    expires_at__gt=timezone.now())
            .order_by("-created_at").first())
    logger.debug("find_intent_by_request: key=%s -> intent_id=%s", req_id, getattr(intent, 'id', None))
    return intent
