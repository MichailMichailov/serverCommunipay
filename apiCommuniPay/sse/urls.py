# urls.py
from django.urls import path
from apiCommuniPay.sse.views import sse_subscribe

urlpatterns = [
    path("<str:token>/", sse_subscribe, name="sse-subscribe"),
]
