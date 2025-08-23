from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthFlowTests(APITestCase):
    def setUp(self):
        self.register_url = "/api/auth/register/"
        self.token_url = "/api/token/"
        self.refresh_url = "/api/token/refresh/"
        self.api_index_url = "/api/"

    def test_register_login_refresh_and_auth_request(self):
        # 1) Регистрация
        payload = {"username": "user1", "email": "u1@example.com", "password": "pass12345"}
        r = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(User.objects.filter(username="user1").exists())

        # 2) Логин → получить access/refresh
        r = self.client.post(self.token_url, {"username":"user1","password":"pass12345"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        access = r.data["access"]
        refresh = r.data["refresh"]
        self.assertTrue(isinstance(access, str) and isinstance(refresh, str))

        # 3) Доступ к защищённому эндпоинту с access
        r = self.client.get(self.api_index_url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data, {"ok": True})

        # 4) Обновление access по refresh
        r = self.client.post(self.refresh_url, {"refresh": refresh}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        new_access = r.data["access"]
        self.assertNotEqual(new_access, access)

    def test_protected_requires_auth(self):
        # Без токена должен быть 401
        r = self.client.get(self.api_index_url)
        self.assertIn(r.status_code, (401, 403))  # зависит от настроек DEFAULT_PERMISSION_CLASSES
