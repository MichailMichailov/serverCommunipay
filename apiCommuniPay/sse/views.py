import time
import json
from django.http import HttpResponseBadRequest, StreamingHttpResponse
from threading import Event

# Временное хранилище активных подписок (in-memory)
SSE_CONNECTIONS = {}  # {token: {"event": Event(), "message": str}}

def sse_subscribe(request, token):
    """
    Подписка на SSE по токену.
    Ожидает сообщения или таймаут 15 минут.
    """
    if request.method != "GET":
        return HttpResponseBadRequest("GET only")
    
    # создаём Event для ожидания сообщения
    stop_event = Event()
    SSE_CONNECTIONS[token] = {"event": stop_event, "message": None}

    def event_stream():
        try:
            # ждём сообщение до 15 минут
            if not stop_event.wait(timeout=15*60):
                # таймаут
                yield "event: timeout\ndata: {}\n\n"
            else:
                msg = SSE_CONNECTIONS[token]["message"]
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            # чистим соединение
            SSE_CONNECTIONS.pop(token, None)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    return response


def send_message_to_token(token: str, payload: dict):
    """
    Отправка сообщения конкретному клиенту по токену.
    """
    conn = SSE_CONNECTIONS.get(token)
    if conn:
        conn["message"] = payload
        conn["event"].set()  # пробуждаем генератор
