"""
Root URL map.

Each app owns its own urls.py so screens stay easy to find:
  pages      — landing, pricing, terms, privacy
  accounts   — register, login, logout, password reset, dashboard
  humanizer  — workspace, history, JSON humanize
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.humanizer.urls")),
    path("", include("apps.pages.urls")),
]
