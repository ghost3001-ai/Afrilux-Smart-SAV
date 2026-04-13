"""
URL configuration for afrilux_sav project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
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

import sys

from django.contrib import admin
from django.conf import settings
from django.contrib.staticfiles.views import serve as serve_staticfiles
from django.urls import include, path, re_path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.views.generic import TemplateView
from django.views.static import serve as serve_media

urlpatterns = [
    path("", include("sav.web_urls")),
    path("admin/", admin.site.urls),
    path("api/docs/", TemplateView.as_view(template_name="sav/api_docs.html"), name="api-docs"),
    path("api/", include(("sav.urls", "sav_api"), namespace="sav_api")),
    path("api/v1/", include(("sav.urls", "sav_api_v1"), namespace="sav_api_v1")),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]

if settings.DEBUG or "runserver" in sys.argv:
    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", serve_staticfiles, {"insecure": True}),
    ]

if settings.DEBUG or settings.SERVE_STATIC_LOCAL or "runserver" in sys.argv:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve_media, {"document_root": settings.MEDIA_ROOT}),
    ]
