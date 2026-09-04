"""Django admin for User, Profile, and the new security models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import LoginAttempt, Profile, User, UserSecurityProfile


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Email-based user list (username field removed)."""

    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_active")
    search_fields = ("email", "name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "password1", "password2"),
            },
        ),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Plan override for support (e.g. gift Pro during demo)."""

    list_display = ("user", "plan", "updated_at")
    list_filter = ("plan",)
    search_fields = ("user__email",)


@admin.action(description="Unlock selected accounts (reset lockout counters)")
def unlock_accounts(modeladmin, request, queryset):
    """Allow a developer to re-enable a permanently or temporarily locked account."""
    queryset.update(
        permanently_locked=False,
        failed_attempts=0,
        lockout_stage=UserSecurityProfile.LOCKOUT_NONE,
        locked_until=None,
    )


@admin.register(UserSecurityProfile)
class UserSecurityProfileAdmin(admin.ModelAdmin):
    """Security profile: lockout state and trusted device/IP."""

    list_display = (
        "user",
        "signup_ip",
        "last_login_ip",
        "failed_attempts",
        "lockout_stage",
        "permanently_locked",
        "updated_at",
    )
    list_filter = ("permanently_locked", "lockout_stage")
    search_fields = ("user__email", "signup_ip", "signup_device_fingerprint")
    readonly_fields = ("user", "created_at", "updated_at")
    actions = [unlock_accounts]


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Audit trail of every login attempt."""

    list_display = ("user", "ip_address", "success", "reason", "created_at")
    list_filter = ("success", "reason")
    search_fields = ("user__email", "ip_address", "device_fingerprint")
    readonly_fields = (
        "user",
        "ip_address",
        "device_fingerprint",
        "success",
        "reason",
        "created_at",
    )
