from django.urls import path

from . import views

app_name = "public"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.results, name="search"),
    path("lost/", views.lost_report, name="lost"),
    path("found/", views.found_report, name="found"),
    path("submitted/", views.submitted, name="submitted"),
    path("claim/done/", views.claim_done, name="claim_done"),
    path("claim/<str:reference>/", views.claim, name="claim"),
    path("how-it-works/", views.how_it_works, name="how"),
    path("privacy/", views.privacy, name="privacy"),
    path("healthz/", views.healthz, name="healthz"),
]
