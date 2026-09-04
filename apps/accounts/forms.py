"""Registration and email-login forms with hard security checks."""

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import LoginAttempt, User
from apps.accounts.security import (
    check_device_binding,
    check_registration_allowed,
    format_lockout_wait,
    is_permanently_locked,
    is_temporarily_locked,
    record_failed_login,
    record_signup,
    record_successful_login,
)


class RegisterForm(UserCreationForm):
    """Create an account with display name, email, and password."""

    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "name", "class": "field-input"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "field-input"}),
    )

    class Meta:
        model = User
        fields = ("name", "email")

    def __init__(self, request=None, *args, **kwargs):
        """Apply the shared input class and capture the request for IP/device checks."""
        super().__init__(*args, **kwargs)
        self.request = request
        self.fields["password1"].widget.attrs["class"] = "field-input"
        self.fields["password2"].widget.attrs["class"] = "field-input"

    def clean_email(self):
        """Enforce one email, one IP, and one device per account."""
        email = self.cleaned_data.get("email")
        if email and self.request:
            check_registration_allowed(self.request, email)
        return email

    def save(self, commit=True):
        """Persist the user, attach the signup device/IP, and create the profile."""
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.name = self.cleaned_data["name"]
        if commit:
            user.save()
            if self.request:
                record_signup(self.request, user)
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """Login form labeled as email (USERNAME_FIELD is still `email`)."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "field-input"}),
    )

    def __init__(self, request=None, *args, **kwargs):
        """Style the password field and capture the request."""
        super().__init__(request=request, *args, **kwargs)
        self.fields["password"].widget.attrs["class"] = "field-input"

    def clean(self):
        """Validate lockout + device binding before the password, then audit the result."""
        email = self.cleaned_data.get("username")
        user = None
        if email:
            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                user = None

            if user:
                if is_permanently_locked(user):
                    raise forms.ValidationError(
                        _(
                            "This account is permanently locked after too many "
                            "failed password attempts. Contact the developer to unlock it."
                        )
                    )

                locked, remaining = is_temporarily_locked(user)
                if locked:
                    # Count probes that arrive during a lock so the next stage
                    # (10 min, then permanent) still escalates.
                    record_failed_login(
                        self.request,
                        user,
                        reason=LoginAttempt.REASON_LOCKED,
                    )
                    raise forms.ValidationError(
                        _(
                            "Too many failed password attempts. Try again in %(wait)s."
                        )
                        % {"wait": format_lockout_wait(remaining)}
                    )

                check_device_binding(self.request, user)

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            # Wrong password for a known user: count toward the lockout timer.
            if user:
                record_failed_login(
                    self.request,
                    user,
                    reason=LoginAttempt.REASON_WRONG_PASSWORD,
                )
            raise

        # Successful login: reset lockout counters and write an audit row.
        if user:
            record_successful_login(self.request, user)
        return cleaned_data


class ConsolePasswordResetForm(PasswordResetForm):
    """Disable password reset for accounts that are permanently locked."""

    def get_users(self, email):
        for user in super().get_users(email):
            if not is_permanently_locked(user):
                yield user
