import json
import time
from django.conf import settings
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
from django.views import View
import redis

def validate_sse_token(token):
    """
    Проверяет токен (пример).
    Реализуйте логику авторизации: токен проекта, JWT, intent token и т.д.
    Верните True если OK, иначе False.
    """
    # TODO: сделать реальную проверку в вашем проекте
    return True if token else False

def sse_format(data: str, event: str = None) -> str:
    """Форматирует строку в SSE-формат"""
    s = ""
    if event:
        s += f"event: {event}\n"
    for line in str(data).splitlines():
        s += f"data: {line}\n"
    s += "\n"
    return s

@method_decorator(require_GET, name="dispatch")
class SubscribeView(View):
    """
    GET /sse/subscribe/<channel>/?token=...
    Возвращает StreamingHttpResponse с content_type 'text/event-stream'
    """
    def get(self, request, channel, *args, **kwargs):
        token = request.GET.get("token")
        if not validate_sse_token(token):
            return StreamingHttpResponse("HTTP/1.1 403 Forbidden", status=403)
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        def event_stream():
            yield sse_format("connected")
            last_heartbeat = time.time()
            try:
                for message in pubsub.listen():
                    mtype = message.get("type")
                    if mtype == "message":
                        data = message.get("data")
                        yield sse_format(data)
                    now = time.time()
                    if now - last_heartbeat > 15:
                        yield ": ping\n\n"
                        last_heartbeat = now
            except GeneratorExit:
                try:
                    pubsub.unsubscribe(channel)
                    pubsub.close()
                except Exception:
                    pass
        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        response["Access-Control-Allow-Origin"] = "*"
        return response
