import json
import redis
import logging
from django.conf import settings

def get_redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)

def publish_event(channel: str, event: dict):
    """
    Публикует JSON-событие в Redis.
    channel: строка (например f"project_{project.id}")
    event: dict, будет сериализован в JSON
    """
    r = get_redis()
    payload = json.dumps(event, default=str)
    r.publish(channel, payload)


def send_sse_message(channel, payload):
    try:
        publish_event(channel, payload)
    except Exception as e:
        logging.exception("Failed to publish SSE event: %s", e)