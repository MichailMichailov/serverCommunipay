from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

class ClubsApiTests(APITestCase):
    def setUp(self):
        # пользователи
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.other = User.objects.create_user(username="other", password="pass12345")
        # базовые урлы
        self.clubs_url = "/api/clubs/"
        self.plans_url = "/api/plans/"
        self.subs_url = "/api/subscriptions/"

    def test_owner_can_create_club(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(self.clubs_url, {"name": "My Club", "slug": "my-club"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["owner"], self.owner.id)

    def test_anon_cannot_create_club(self):
        r = self.client.post(self.clubs_url, {"name": "Nope", "slug": "nope"}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_other_cannot_patch_foreign_club(self):
        # создаёт владелец
        self.client.force_authenticate(self.owner)
        r = self.client.post(self.clubs_url, {"name": "EditMe", "slug": "edit-me"}, format="json")
        club_id = r.data["id"]
        # другой пользователь пытается изменить
        self.client.force_authenticate(self.other)
        r = self.client.patch(f"{self.clubs_url}{club_id}/", {"name": "Hacked"}, format="json")
        self.assertIn(r.status_code, (403, 404))

    def test_owner_can_create_plan_for_own_club(self):
        self.client.force_authenticate(self.owner)
        club = self.client.post(self.clubs_url, {"name":"C1","slug":"c1"}, format="json").data
        payload = {"club": club["id"], "title": "Basic", "price": "99.00", "period":"month", "trial_days":7, "is_public": True}
        r = self.client.post(self.plans_url, payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_other_cannot_create_plan_in_foreign_club(self):
        # клуб создаёт владелец
        self.client.force_authenticate(self.owner)
        club = self.client.post(self.clubs_url, {"name":"C2","slug":"c2"}, format="json").data
        # другой пытается создать план
        self.client.force_authenticate(self.other)
        r = self.client.post(self.plans_url, {"club": club["id"], "title":"Nope", "price":"1.00", "period":"month"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_public_plans_visible_to_anon_and_filter_by_club(self):
        # создаём два клуба и планы
        self.client.force_authenticate(self.owner)
        c1 = self.client.post(self.clubs_url, {"name":"C3","slug":"c3"}, format="json").data
        c2 = self.client.post(self.clubs_url, {"name":"C4","slug":"c4"}, format="json").data
        self.client.post(self.plans_url, {"club": c1["id"], "title":"P1","price":"10.00","period":"month","is_public":True}, format="json")
        self.client.post(self.plans_url, {"club": c2["id"], "title":"P2","price":"20.00","period":"month","is_public":True}, format="json")

        # аноним видит публичные
        self.client.force_authenticate(None)
        r = self.client.get(self.plans_url)
        self.assertEqual(r.status_code, 200)
        # пагинация включена → будет объект {count, results, ...}
        self.assertIn("count", r.data)
        self.assertIn("results", r.data)
        self.assertGreaterEqual(r.data["count"], 2)

        # фильтр по club
        r = self.client.get(self.plans_url, {"club": c1["id"]})
        self.assertEqual(r.status_code, 200)
        titles = [p["title"] for p in r.data["results"]]
        self.assertTrue(all(t in {"P1"} for t in titles))

    def test_pagination_on_plans(self):
        self.client.force_authenticate(self.owner)
        c = self.client.post(self.clubs_url, {"name":"C5","slug":"c5"}, format="json").data
        for i in range(3):
            self.client.post(self.plans_url, {"club": c["id"], "title": f"P{i}", "price":"1.00","period":"month","is_public":True}, format="json")

        self.client.force_authenticate(None)
        r1 = self.client.get(self.plans_url)  # PAGE_SIZE=2
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.data["count"], 3)
        self.assertEqual(len(r1.data["results"]), 2)

        r2 = self.client.get(self.plans_url, {"page": 2})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.data["results"]), 1)

    def test_user_creates_subscription_and_cancel(self):
        # владелец делает публичный план с триалом
        self.client.force_authenticate(self.owner)
        club = self.client.post(self.clubs_url, {"name":"C6","slug":"c6"}, format="json").data
        plan = self.client.post(self.plans_url, {"club": club["id"], "title":"Trial","price":"50.00","period":"month","trial_days":7,"is_public":True}, format="json").data

        # другой пользователь подписывается
        self.client.force_authenticate(self.other)
        r = self.client.post(self.subs_url, {"plan": plan["id"]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        sub_id = r.data["id"]
        self.assertEqual(r.data["status"], "trial")

        # только свои подписки видны
        r_list = self.client.get(self.subs_url)
        self.assertEqual(r_list.status_code, 200)
        ids = [s["id"] for s in r_list.data["results"]] if isinstance(r_list.data, dict) else [s["id"] for s in r_list.data]
        self.assertIn(sub_id, ids)

        # отмена
        r_cancel = self.client.post(f"{self.subs_url}{sub_id}/cancel/")
        self.assertEqual(r_cancel.status_code, 200)
