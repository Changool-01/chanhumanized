"""
User and Profile models.

Email is the login field (no username). Plan lives on Profile so billing can
attach later without rewriting auth.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Create users with email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Normalize email, require it, and save the user."""
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create a regular (non-staff) user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create a Django admin superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Site member. Logs in with email; display name is stored in `name`."""

    username = None
    email = models.EmailField("email address", unique=True)
    name = models.CharField(max_length=150)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        """Show email in admin lists."""
        return self.email

    def get_short_name(self):
        """First token of the display name, used in the header."""
        return (self.name or self.email).split()[0]


class Profile(models.Model):
    """Per-user plan. Stripe fields can be added later without touching User."""

    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_CHOICES = (
        (PLAN_FREE, "Free"),
        (PLAN_PRO, "Pro"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, default=PLAN_FREE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "profile"
        verbose_name_plural = "profiles"

    def __str__(self):
        """Show who owns the profile."""
        return f"{self.user.email} ({self.plan})"

    def is_pro(self):
        """Return True when the user is on the Pro plan."""
        return self.plan == self.PLAN_PRO


class UserSecurityProfile(models.Model):
    """Hard-security data for a user: lockout state and trusted device/IP."""

    LOCKOUT_NONE = 0
    LOCKOUT_ONE_MINUTE = 1
    LOCKOUT_TEN_MINUTES = 2
    LOCKOUT_PERMANENT = 3
    LOCKOUT_CHOICES = (
        (LOCKOUT_NONE, "None"),
        (LOCKOUT_ONE_MINUTE, "1 minute"),
        (LOCKOUT_TEN_MINUTES, "10 minutes"),
        (LOCKOUT_PERMANENT, "Permanent"),
    )

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="security_profile"
    )
    signup_ip = models.CharField(max_length=64, blank=True, db_index=True)
    signup_device_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    last_login_ip = models.CharField(max_length=64, blank=True)
    last_login_device_fingerprint = models.CharField(max_length=64, blank=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    lockout_stage = models.PositiveSmallIntegerField(
        choices=LOCKOUT_CHOICES, default=LOCKOUT_NONE
    )
    locked_until = models.DateTimeField(null=True, blank=True)
    permanently_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "security profile"
        verbose_name_plural = "security profiles"

    def __str__(self):
        """Admin label."""
        return f"{self.user.email} · {self.get_lockout_stage_display()}"


class LoginAttempt(models.Model):
    """Audit trail of every login attempt, successful or failed."""

    REASON_SUCCESS = "success"
    REASON_WRONG_PASSWORD = "wrong_password"
    REASON_DEVICE_MISMATCH = "device_mismatch"
    REASON_IP_MISMATCH = "ip_mismatch"
    REASON_LOCKED = "locked"
    REASON_CHOICES = (
        (REASON_SUCCESS, "Success"),
        (REASON_WRONG_PASSWORD, "Wrong password"),
        (REASON_DEVICE_MISMATCH, "Device mismatch"),
        (REASON_IP_MISMATCH, "IP mismatch"),
        (REASON_LOCKED, "Already locked"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="login_attempts",
    )
    ip_address = models.CharField(max_length=64, blank=True, db_index=True)
    device_fingerprint = models.CharField(max_length=64, blank=True)
    success = models.BooleanField(default=False)
    reason = models.CharField(max_length=32, choices=REASON_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "login attempt"
        verbose_name_plural = "login attempts"

    def __str__(self):
        """Admin label."""
        return f"{self.user or 'anonymous'} · {self.ip_address} · {self.get_reason_display()}"
