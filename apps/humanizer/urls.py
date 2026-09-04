"""Humanizer routes: workspace, JSON API, history."""

from django.urls import path

from apps.humanizer import views

app_name = "humanizer"

urlpatterns = [
    path("app/", views.workspace, name="workspace"),
    path("app/humanize/", views.humanize_api, name="humanize_api"),
    path("history/", views.history_list, name="history"),
    path("history/<int:job_id>/", views.history_detail, name="history_detail"),
]
