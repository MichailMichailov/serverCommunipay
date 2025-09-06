"""
URL configuration for apiCommuniPay project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from django.urls import path
from django.http import HttpResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from apiCommuniPay.clubs.views import ChatAccessView
from django.conf import settings
from django.conf.urls.static import static



def healthz(_): return HttpResponse(status=204)


# urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView, RedirectView
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
# healthz как было
 # или откуда у тебя healthz

@method_decorator(never_cache, name="dispatch")
class SPAView(TemplateView):
    template_name = "index.html"  # /app/templates/index.html

def healthz(_): return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    # API первыми, чтобы не перехватывались SPA-роутером
    path("api/", include("apiCommuniPay.api.urls")),
    path("api/", include("apiCommuniPay.clubs.urls")),
    path("api/", include("apiCommuniPay.projects.urls")),
    path("api/common/", include(("apiCommuniPay.common.urls", "common"), namespace="common")),
    path("api/sse/", include("apiCommuniPay.sse.urls")),
    path("healthz", healthz),
    # healthchecks
    path("api/healthz", healthz, name="healthz"),
    path("healthz", healthz),

    # админка
    path("admin/", admin.site.urls),
    path("admin", RedirectView.as_view(url="/admin/", permanent=True)),

    # SPA на корень
    path("", SPAView.as_view(), name="spa"),

    # и catch-all для любых других путей, КРОМЕ api/admin/healthz:
    re_path(r"^(?!api/|admin/|healthz$).*$", SPAView.as_view(), name="spa-catchall"),
    path("api/chats/<int:pk>/access/", ChatAccessView.as_view(), name="chat-access"),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
