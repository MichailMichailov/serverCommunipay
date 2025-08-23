from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient

User = get_user_model()


class PlansApiTests(APITestCase):
    clubs_url = "/api/clubs/"
    plans_url = "/api/plans/"

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="o@example.com", password="pass")
        self.other = User.objects.create_user(username="other", email="x@example.com", password="pass")
        self.client = APIClient()

    def auth_as_owner(self):
        self.client.force_authenticate(self.owner)

    def auth_as_other(self):
        self.client.force_authenticate(self.other)

    def test_owner_can_create_plan_for_own_project(self):
        self.auth_as_owner()
        club = self.client.post(self.clubs_url, {"name": "C1", "slug": "c1"}, format="json").data
        payload = {"project": club["project"], "name": "P1", "price": "10.00", "is_public": True}
        r = self.client.post(self.plans_url, payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["name"], "P1")
        self.assertEqual(str(r.data["project"]), str(club["project"]))

    def test_other_cannot_create_plan_in_foreign_project(self):
        # проект создан владельцем
        self.auth_as_owner()
        club = self.client.post(self.clubs_url, {"name": "C2", "slug": "c2"}, format="json").data

        # другой юзер пытается создать план в чужом проекте
        self.auth_as_other()
        r = self.client.post(self.plans_url, {"project": club["project"], "name": "Nope", "price": "1.00"}, format="json")
        self.assertIn(r.status_code, (403, 404), r.content)

    def test_public_plans_visible_to_anon_and_filter_by_project(self):
        # создаём два проекта и по публичному плану в каждом
        self.auth_as_owner()
        c1 = self.client.post(self.clubs_url, {"name": "C3", "slug": "c3"}, format="json").data
        c2 = self.client.post(self.clubs_url, {"name": "C4", "slug": "c4"}, format="json").data
        self.client.post(self.plans_url, {"project": c1["project"], "name": "P1", "price": "10.00", "is_public": True}, format="json")
        self.client.post(self.plans_url, {"project": c2["project"], "name": "P2", "price": "20.00", "is_public": True}, format="json")

        # аноним видит публичные планы
        self.client.logout()
        r_all = self.client.get(self.plans_url)
        self.assertGreaterEqual(r_all.data.get("count", len(r_all.data if isinstance(r_all.data, list) else [])), 2)

        # фильтр по project
        r_filtered = self.client.get(self.plans_url, {"project": c1["project"]})
        # универсальная проверка для пагинированного и непагинированного ответа
        if isinstance(r_filtered.data, dict) and "results" in r_filtered.data:
            items = r_filtered.data["results"]
        else:
            items = r_filtered.data
        self.assertTrue(len(items) >= 1)
        for item in items:
            self.assertEqual(str(item["project"]), str(c1["project"]))
