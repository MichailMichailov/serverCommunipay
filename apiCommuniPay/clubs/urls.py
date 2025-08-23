from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import ClubViewSet, PlanViewSet, SubscriptionViewSet

router = DefaultRouter()
router.register("clubs", ClubViewSet, basename="club")
router.register("plans", PlanViewSet, basename="plan")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")

urlpatterns = [path("", include(router.urls))]
