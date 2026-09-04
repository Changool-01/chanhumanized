"""App config for accounts."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Registers the accounts app and creates a Profile when a User is saved."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"

    def ready(self):
        """Import signal handlers after the app registry is populated."""
        from apps.accounts import signals  # noqa: F401
