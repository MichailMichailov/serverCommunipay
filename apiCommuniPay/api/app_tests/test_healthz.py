from django.urls import reverse
from rest_framework.test import APITestCase

class HealthzTests(APITestCase):
    def test_healthz_returns_204(self):
        url = "/api/healthz"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b"")
