from rest_framework import serializers, views, response, status, permissions
from django.contrib.auth import get_user_model
from apiCommuniPay.accounts.models import Roles

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, data):
        # username обязателен по умолчанию; email — опционально
        return User.objects.create_user(
            username=data["username"],
            email=data.get("email") or "",
            password=data["password"],
            role=Roles.MEMBER,
        )

class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return response.Response(
            {"id": user.id, "username": user.username},
            status=status.HTTP_201_CREATED,
        )
