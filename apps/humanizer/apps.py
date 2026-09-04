"""App config for the humanizer."""

from django.apps import AppConfig


class HumanizerConfig(AppConfig):
    """Registers rewrite jobs and the workspace."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.humanizer"
    label = "humanizer"
    verbose_name = "Humanizer"
