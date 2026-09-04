"""Create profile and security rows whenever a User is created."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Profile, User, UserSecurityProfile


@receiver(post_save, sender=User)
def create_profile_for_user(sender, instance, created, **kwargs):
    """Attach a Free Profile to every new User."""
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def create_security_profile_for_user(sender, instance, created, **kwargs):
    """Attach a Security Profile to every new User."""
    if created:
        UserSecurityProfile.objects.get_or_create(user=instance)
