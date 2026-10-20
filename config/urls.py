from django.conf import settings
from django.contrib import admin
from django.urls import include, path

handler404 = "search.views.error_404"
handler500 = "search.views.error_500"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("staff/", include("dashboard.urls")),
    path("", include("search.urls")),
]
