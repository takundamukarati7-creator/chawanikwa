from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("login/", views.StaffLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", views.overview, name="overview"),
    path("found/", views.found_list, name="found_list"),
    path("found/<int:pk>/", views.found_detail, name="found_detail"),
    path("lost/", views.lost_list, name="lost_list"),
    path("lost/<int:pk>/", views.lost_detail, name="lost_detail"),
    path("matches/", views.match_list, name="match_list"),
    path("matches/<int:pk>/contacted/", views.match_contacted, name="match_contacted"),
    path("claims/", views.claim_list, name="claim_list"),
    path("claims/<int:pk>/", views.claim_detail, name="claim_detail"),
    path("audit/", views.audit_list, name="audit_list"),
]
