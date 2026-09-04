"""Put the public product name on every template."""

from django.conf import settings


def site_branding(request):
    """Expose SITE_NAME as `site_name` in all templates."""
    return {"site_name": settings.SITE_NAME}
