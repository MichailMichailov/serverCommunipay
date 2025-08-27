# apiCommuniPay/common/tg.py
from __future__ import annotations
import requests
from django.conf import settings

TG_API = "https://api.telegram.org"

def tg_api(method: str, **params):
    url = f"{TG_API}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.post(url, json=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data["result"]

def get_chat(chat_id: int) -> dict:
    return tg_api("getChat", chat_id=chat_id)

def get_bot_id() -> int:
    # Можно задать TELEGRAM_BOT_ID в settings/env,
    # но если не задан, спросим у Telegram и закэшируем в модуле.
    bot_id = getattr(settings, "TELEGRAM_BOT_ID", None)
    if bot_id:
        return int(bot_id)
    if not hasattr(get_bot_id, "_cache"):
        me = tg_api("getMe")
        get_bot_id._cache = int(me["id"])
    return get_bot_id._cache
