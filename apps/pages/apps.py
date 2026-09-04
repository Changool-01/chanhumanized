"""App config for static pages."""

from django.apps import AppConfig


class PagesConfig(AppConfig):
    """Landing, pricing, and legal placeholder pages."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pages"
    label = "pages"
    verbose_name = "Pages"
