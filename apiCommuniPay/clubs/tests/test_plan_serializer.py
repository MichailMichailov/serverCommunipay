from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apiCommuniPay.projects.models import Project, ProjectMember
from apiCommuniPay.common.models import TelegramChat
from apiCommuniPay.clubs.models import Plan
from apiCommuniPay.clubs.serializers import PlanSerializer

User = get_user_model()


class PlanSerializerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", email="o@example.com", password="pass")
        self.project = Project.objects.create(owner=self.owner, name="Proj", slug="proj")
        ProjectMember.objects.create(project=self.project, user=self.owner, role="owner")

        # чат/канал внутри проекта
        self.chat = TelegramChat.objects.create(
            project=self.project,
            chat_id=123456789,
            title="Main Channel",
            is_channel=True,
        )

    def test_serialize_plan_minimal(self):
        plan = Plan.objects.create(
            project=self.project,
            name="Basic",
            price=Decimal("9.99"),
            is_public=True,
        )
        ser = PlanSerializer(instance=plan)
        data = ser.data

        self.assertEqual(data["name"], "Basic")
        self.assertEqual(str(data["project"]), str(self.project.id))
        # Decimal обычно уходит строкой
        self.assertIn(data["price"], ("9.99", "9.990", "9.9900"))

        # channels присутствует (пустой список по умолчанию)
        self.assertIn("channels", data)
        self.assertIsInstance(data["channels"], list)
        self.assertEqual(len(data["channels"]), 0)

    def test_serialize_plan_with_channels(self):
        plan = Plan.objects.create(
            project=self.project,
            name="Pro",
            price=Decimal("19.00"),
            is_public=False,
        )
        plan.channels.add(self.chat)

        ser = PlanSerializer(instance=plan)
        data = ser.data

        self.assertEqual(data["name"], "Pro")
        self.assertIn("channels", data)
        self.assertEqual(len(data["channels"]), 1)

        # допускаем оба варианта представления: id или объект {id: ...}
        item = data["channels"][0]
        if isinstance(item, dict):
            self.assertEqual(item.get("id"), self.chat.id)
        else:
            self.assertEqual(item, self.chat.id)
