"""Security helpers: IP/device fingerprint extraction, lockout, and alerts.

These are used by forms, views, and middleware to enforce the pre-deployment
security rules requested for the free PythonAnywhere deployment:
  - one email / one IP / one device per account
  - escalating password-attempt lockout (1 min -> 10 min -> permanent)
  - developer email alerts on permanent lockout
"""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import LoginAttempt, UserSecurityProfile

# Lockout thresholds described by the owner:
# 5 wrong passwords -> 1 minute lock
# 3 more wrong passwords -> 10 minute lock
# 1 more wrong password -> permanent lock (email developer)
STAGE_1_ATTEMPTS = 5
STAGE_1_LOCK_SECONDS = 60
STAGE_2_ATTEMPTS = STAGE_1_ATTEMPTS + 3  # 8
STAGE_2_LOCK_SECONDS = 600  # 10 minutes
STAGE_3_ATTEMPTS = STAGE_2_ATTEMPTS + 1  # 9


def get_client_ip(request):
    """Return the client IP, trusting the PythonAnywhere proxy header first."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # The leftmost value is the end-user IP supplied by the proxy chain.
        ip = x_forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR") or "0.0.0.0"


def get_device_fingerprint(request):
    """Return a stable, privacy-safe hash of the device headers.

    We intentionally do NOT store the raw User-Agent. A SHA-256 hash of the
    header bundle is enough to distinguish devices without keeping PII.
    """
    parts = [
        request.META.get("HTTP_USER_AGENT", ""),
        request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
        request.META.get("HTTP_ACCEPT_ENCODING", ""),
        request.META.get("HTTP_DNT", ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def format_lockout_wait(seconds):
    """Human-readable remaining lockout time."""
    if seconds <= 0:
        return "a moment"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    if minutes:
        if sec:
            return f"{minutes} minute{'s' if minutes != 1 else ''} {sec} second{'s' if sec != 1 else ''}"
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{sec} second{'s' if sec != 1 else ''}"


def get_security_profile(user):
    """Return the security profile for a user, creating one if necessary."""
    return UserSecurityProfile.objects.get_or_create(user=user)[0]


def is_permanently_locked(user):
    """True if the account has been locked forever."""
    try:
        return user.security_profile.permanently_locked
    except UserSecurityProfile.DoesNotExist:
        return False


def is_temporarily_locked(user):
    """Return (locked, seconds_remaining) for the current lockout timer."""
    try:
        sp = user.security_profile
    except UserSecurityProfile.DoesNotExist:
        return False, 0

    if sp.locked_until and sp.locked_until > timezone.now():
        return True, int((sp.locked_until - timezone.now()).total_seconds())
    return False, 0


def check_lockout(user):
    """Raise ValidationError if the user is currently locked out."""
    if is_permanently_locked(user):
        raise ValidationError(
            _(
                "This account is permanently locked after too many failed password "
                "attempts. Contact the developer to unlock it."
            )
        )

    locked, seconds = is_temporarily_locked(user)
    if locked:
        raise ValidationError(
            _(
                "Too many failed password attempts. Please try again in %(wait)s."
            )
            % {"wait": format_lockout_wait(seconds)}
        )


def check_device_binding(request, user):
    """Raise ValidationError if the login device does not match the signup device.

    Strict mode binds each account to the device that was used to register it.
    IP is also captured for registration uniqueness, but the device fingerprint
    is the primary binding because home/mobile IPs change.
    """
    if not settings.SECURITY_STRICT_DEVICE_IP:
        return

    try:
        sp = user.security_profile
    except UserSecurityProfile.DoesNotExist:
        return

    if not sp.signup_device_fingerprint:
        return

    device = get_device_fingerprint(request)
    if device != sp.signup_device_fingerprint:
        LoginAttempt.objects.create(
            user=user,
            ip_address=get_client_ip(request),
            device_fingerprint=device,
            success=False,
            reason="device_mismatch",
        )
        raise ValidationError(
            _(
                "This account is locked to the device used during registration. "
                "Contact the developer to register a new device."
            )
        )


def record_successful_login(request, user):
    """Reset lockout counters and record a successful login attempt."""
    sp = get_security_profile(user)
    sp.failed_attempts = 0
    sp.lockout_stage = 0
    sp.locked_until = None
    sp.last_login_ip = get_client_ip(request)
    sp.last_login_device_fingerprint = get_device_fingerprint(request)
    sp.save()

    LoginAttempt.objects.create(
        user=user,
        ip_address=sp.last_login_ip,
        device_fingerprint=sp.last_login_device_fingerprint,
        success=True,
        reason="success",
    )


def _send_permanent_lockout_alert(user, attempt):
    """Email the developer when an account is permanently locked."""
    if not settings.SECURITY_EMAIL_ON_LOCKOUT or not settings.DEVELOPER_EMAIL:
        return

    subject = f"SECURITY: Account permanently locked - {user.email}"
    body = (
        f"Account: {user.email} (id={user.pk})\n"
        f"Time: {timezone.now().isoformat()}\n"
        f"IP: {attempt.ip_address}\n"
        f"Device fingerprint: {attempt.device_fingerprint}\n"
        f"Total failed attempts: {user.security_profile.failed_attempts}\n\n"
        "Action required: unlock the account in the admin and contact the user "
        "if they requested access."
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEVELOPER_EMAIL],
            fail_silently=True,
        )
    except Exception:
        # Never let an email failure stop the login flow.
        pass


def record_failed_login(request, user, reason="wrong_password"):
    """Record a failed login and update the escalating lockout timer."""
    sp = get_security_profile(user)
    sp.failed_attempts += 1

    now = timezone.now()
    if sp.failed_attempts >= STAGE_3_ATTEMPTS:
        sp.permanently_locked = True
        sp.lockout_stage = 3
        sp.locked_until = None
    elif sp.failed_attempts >= STAGE_2_ATTEMPTS:
        sp.lockout_stage = 2
        sp.locked_until = now + timedelta(seconds=STAGE_2_LOCK_SECONDS)
    elif sp.failed_attempts >= STAGE_1_ATTEMPTS:
        sp.lockout_stage = 1
        sp.locked_until = now + timedelta(seconds=STAGE_1_LOCK_SECONDS)
    sp.save()

    attempt = LoginAttempt.objects.create(
        user=user,
        ip_address=get_client_ip(request),
        device_fingerprint=get_device_fingerprint(request),
        success=False,
        reason=reason,
    )

    if sp.permanently_locked:
        _send_permanent_lockout_alert(user, attempt)


def check_registration_allowed(request, email):
    """Raise ValidationError if the signup IP/device is already tied to another account."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    ip = get_client_ip(request)
    device = get_device_fingerprint(request)

    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError(
            _("An account with this email already exists.")
        )

    if (
        UserSecurityProfile.objects.filter(signup_ip=ip)
        .exclude(user__email__iexact=email)
        .exists()
    ):
        raise ValidationError(
            _(
                "An account has already been created from this IP address. "
                "Only one account per IP is allowed."
            )
        )

    if (
        UserSecurityProfile.objects.filter(signup_device_fingerprint=device)
        .exclude(user__email__iexact=email)
        .exists()
    ):
        raise ValidationError(
            _(
                "An account has already been created from this device. "
                "Only one account per device is allowed."
            )
        )


def record_signup(request, user):
    """Store the signup IP/device fingerprint on the new account."""
    sp = get_security_profile(user)
    sp.signup_ip = get_client_ip(request)
    sp.signup_device_fingerprint = get_device_fingerprint(request)
    sp.save()
