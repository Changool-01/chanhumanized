"""Public site routes."""

from django.urls import path

from apps.pages import views

app_name = "pages"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("pricing/", views.PricingView.as_view(), name="pricing"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
]
