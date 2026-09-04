"""Simple template views for public pages."""

from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Quiet landing page with three steps and two calls to action."""

    template_name = "pages/home.html"


class PricingView(TemplateView):
    """Free vs Pro cards. Stripe is not wired in this build."""

    template_name = "pages/pricing.html"


class TermsView(TemplateView):
    """Short terms placeholder until legal copy is written."""

    template_name = "pages/terms.html"


class PrivacyView(TemplateView):
    """Short privacy placeholder until legal copy is written."""

    template_name = "pages/privacy.html"
