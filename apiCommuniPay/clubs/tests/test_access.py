from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient

User = get_user_model()


class AccessTests(APITestCase):
    clubs_url = "/api/clubs/"

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="o@example.com", password="pass")
        self.other = User.objects.create_user(username="other", email="x@example.com", password="pass")
        self.client = APIClient()

    def auth_as_owner(self):
        self.client.force_authenticate(self.owner)

    def auth_as_other(self):
        self.client.force_authenticate(self.other)

    def test_owner_can_create_club(self):
        self.auth_as_owner()
        r = self.client.post(self.clubs_url, {"name": "C1", "slug": "c1"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        # клуб возвращает project id — пригодится в других тестах
        self.assertIn("project", r.data)

    def test_anon_cannot_create_club(self):
        r = self.client.post(self.clubs_url, {"name": "C0", "slug": "c0"}, format="json")
        self.assertIn(r.status_code, (401, 403))  # в зависимости от настроек аутентификации

    def test_other_cannot_patch_foreign_club(self):
        self.auth_as_owner()
        club = self.client.post(self.clubs_url, {"name": "C2", "slug": "c2"}, format="json").data
        club_id = club["id"]

        self.auth_as_other()
        r2 = self.client.patch(f"{self.clubs_url}{club_id}/", {"name": "X"}, format="json")
        # где-то может быть 403, где-то 404 (если скрываем чужие объекты)
        self.assertIn(r2.status_code, (403, 404), r2.content)
