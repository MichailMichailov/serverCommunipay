from rest_framework import serializers
from .models import Plan, Subscription
from apiCommuniPay.common.models import TelegramChat


class PlanSerializer(serializers.ModelSerializer):
    # совместимость со старым API
    title = serializers.CharField(write_only=True, required=False)

    # важно: name больше НЕ обязателен – мы подставим его из title
    name = serializers.CharField(required=False)

    channels = serializers.PrimaryKeyRelatedField(
        many=True, queryset=TelegramChat.objects.all(), required=False
    )

    class Meta:
        model = Plan
        fields = ("id", "project", "name", "title", "price", "is_public", "channels")
        # project больше не read_only — мы выставим его из club в validate()
        read_only_fields = ("id",)

    def validate(self, attrs):
        # name <- title (совместимость)
        title = attrs.pop("title", None)
        if not attrs.get("name") and title:
            attrs["name"] = title

        return attrs

    def create(self, validated_data):
        channels = validated_data.pop("channels", [])
        plan = Plan.objects.create(**validated_data)
        if channels:
            plan.channels.set(channels)
        return plan

    def update(self, instance, validated_data):
        channels = validated_data.pop("channels", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if channels is not None:
            instance.channels.set(channels)
        return instance


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_detail = PlanSerializer(source="plan", read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id","user","plan","plan_detail","status",
            "current_period_start","current_period_end",
            "cancel_at_period_end","created_at"
        ]
        read_only_fields = ["id","status","created_at","user","current_period_start","current_period_end"]
