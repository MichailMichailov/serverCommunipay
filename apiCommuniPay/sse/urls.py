from django.urls import path
from .views import SubscribeView

urlpatterns = [
    path("subscribe/<str:channel>/", SubscribeView.as_view(), name="sse-subscribe"),
]