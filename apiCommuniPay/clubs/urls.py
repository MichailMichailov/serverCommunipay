from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import PlanViewSet, SubscriptionViewSet, ChatAccessView

router = DefaultRouter()
router.register(r"plans", PlanViewSet, basename="plan")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")

urlpatterns = [
    path("", include(router.urls)),
    path("chats/<int:pk>/access/", ChatAccessView.as_view(), name="chat-access"),
]
