from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Project, ProjectMember

User = get_user_model()


class ProjectMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    tg_id = serializers.SerializerMethodField()
    class Meta:
        model = ProjectMember
        fields = ["id", "user", "user_email", "user_name", "role", "joined_at","tg_id"]
        read_only_fields = ["id", "joined_at", "user_email", "user_name", "tg_id"]
    def get_tg_id(self, obj):
        return obj.user.telegram_id if obj.user else None

class ProjectSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()
    members_count = serializers.IntegerField(source="memberships.count", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "slug", "name", "description", "is_active",
            "owner", "created_at", "updated_at",
            "my_role", "members_count",
        ]
        read_only_fields = ["id", "slug", "owner", "created_at", "updated_at", "my_role", "members_count"]

    def get_my_role(self, obj: Project):
        user = self.context["request"].user
        try:
            return obj.memberships.get(user=user).role
        except ProjectMember.DoesNotExist:
            return None

    def create(self, validated_data):
        request = self.context["request"]
        project = Project.objects.create(owner=request.user, **validated_data)
        # сигнал создаст membership владельца
        return project
