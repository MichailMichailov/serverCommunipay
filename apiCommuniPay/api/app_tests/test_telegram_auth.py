import json, time, hmac, hashlib
from urllib.parse import urlencode
from django.test import override_settings
from rest_framework.test import APITestCase

def build_init_data(bot_token: str, payload: dict) -> str:
    secret = hashlib.sha256(bot_token.encode()).digest()
    pairs = {k: str(v) for k, v in payload.items()}
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    hash_hex = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    pairs["hash"] = hash_hex
    return urlencode(pairs)

@override_settings(TELEGRAM_BOT_TOKEN="123:ABC")
class TelegramAuthTests(APITestCase):
    def test_telegram_login_creates_user_and_returns_tokens(self):
        user_json = json.dumps({"id": 424242, "first_name": "Alice", "username": "alice"})
        payload = {"user": user_json, "auth_date": int(time.time())}
        init_data = build_init_data("123:ABC", payload)

        r = self.client.post("/api/auth/telegram/", {"initData": init_data}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)

        # доступ к защищённому ресурсу
        access = r.data["access"]
        r2 = self.client.get("/api/", HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data, {"ok": True})
