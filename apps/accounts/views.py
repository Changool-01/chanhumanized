"""Auth pages and the usage dashboard — rate-limited and security-aware."""

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordResetView
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from apps.accounts.forms import (
    ConsolePasswordResetForm,
    EmailAuthenticationForm,
    RegisterForm,
)
from apps.accounts.ratelimit import rate_limit
from apps.humanizer.services.quota import quota_snapshot


@method_decorator(
    rate_limit(key="ip", rate="5/h", group="register"), name="dispatch"
)
class RegisterView(FormView):
    """Create an account and sign the user in immediately."""

    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("humanizer:workspace")

    def get_form_kwargs(self):
        """Pass the request object so the form can read IP/device headers."""
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        """Save the user, log them in, then send them to the workspace."""
        user = form.save()
        login(self.request, user)
        return super().form_valid(form)


@method_decorator(
    rate_limit(key="ip", rate="10/m", group="login"), name="dispatch"
)
class EmailLoginView(LoginView):
    """Email + password sign-in."""

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class EmailLogoutView(LogoutView):
    """End the session and return to the landing page."""

    next_page = reverse_lazy("pages:home")


@method_decorator(
    rate_limit(key="ip", rate="3/h", group="password_reset"), name="dispatch"
)
class ConsolePasswordResetView(PasswordResetView):
    """
    Standard Django reset flow, but disabled for permanently-locked accounts.
    Email is printed to the server console (EMAIL_BACKEND is console) so the
    PythonAnywhere demo still works.
    """

    template_name = "accounts/password_reset.html"
    form_class = ConsolePasswordResetForm
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_context = {"site_name": settings.SITE_NAME}


@login_required
@rate_limit(key="user", rate="60/m", group="dashboard")
def dashboard(request):
    """Show plan, words used this week, and remaining quota."""
    snapshot = quota_snapshot(request.user)
    return render(
        request,
        "accounts/dashboard.html",
        {
            "snapshot": snapshot,
            "pro_price": "4.99",
            "site_name": settings.SITE_NAME,
        },
    )
