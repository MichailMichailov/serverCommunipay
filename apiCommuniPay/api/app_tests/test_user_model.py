from django.test import TestCase
from django.contrib.auth import get_user_model
from apiCommuniPay.accounts.models import Roles

User = get_user_model()

class UserModelTests(TestCase):
    def test_create_user_with_role_member_by_default(self):
        u = User.objects.create_user(username="m1", password="x")
        self.assertEqual(u.role, Roles.MEMBER)
        self.assertFalse(u.is_platform_staff)

    def test_platform_staff_property(self):
        a = User.objects.create_user(username="adm", password="x", role=Roles.ADMIN)
        s = User.objects.create_superuser(username="root", password="x", role=Roles.SUPERADMIN)
        self.assertTrue(a.is_platform_staff)
        self.assertTrue(s.is_platform_staff)

    # def test_create_superuser_requires_is_staff_superuser(self):
    #     s = User.objects.create_superuser(username="root2", password="x")
    #     self.assertTrue(s.is_superuser)
    #     self.assertTrue(s.is_staff)
