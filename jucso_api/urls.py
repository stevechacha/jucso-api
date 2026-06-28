from django.contrib import admin
from django.urls import include, path

from core.views import RootView

urlpatterns = [
    path("", RootView.as_view(), name="root"),
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
]
