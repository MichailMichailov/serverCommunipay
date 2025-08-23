from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class RegisterValidationTests(APITestCase):
    def setUp(self):
        self.url = "/api/auth/register/"

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(username="u1", email="dupe@ex.com", password="x")
        r = self.client.post(self.url, {"username":"u2","email":"dupe@ex.com","password":"Passw0rd!"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)

class PasswordChangeTests(APITestCase):
    def setUp(self):
        self.url = "/api/auth/password/change/"
        self.user = User.objects.create_user(username="u1", email="u1@ex.com", password="Passw0rd!")

    def test_requires_auth(self):
        r = self.client.post(self.url, {"old_password":"x","new_password":"y"}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_change_password_ok(self):
        self.client.login(username="u1", password="Passw0rd!")
        r = self.client.post(self.url, {"old_password":"Passw0rd!","new_password":"NewStrongPass123"}, format="json")
        self.assertEqual(r.status_code, 204)
        # убеждаемся, что старый пароль не работает
        self.client.logout()
        ok_old = self.client.login(username="u1", password="Passw0rd!")
        self.assertFalse(ok_old)
        ok_new = self.client.login(username="u1", password="NewStrongPass123")
        self.assertTrue(ok_new)
