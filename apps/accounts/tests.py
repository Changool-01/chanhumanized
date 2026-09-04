"""Account and page tests: register, login, dashboard, public screens."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import LoginAttempt, User, UserSecurityProfile


class PublicPagesTests(TestCase):
    """Landing and pricing should load without an account."""

    def test_home_shows_product_name(self):
        """Home page uses the Chan Humanized AI brand."""
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chan Humanized AI")

    def test_pricing_has_free_and_pro(self):
        """Pricing shows only Free and Pro."""
        response = self.client.get(reverse("pages:pricing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100,000")
        self.assertContains(response, "$4.99")


class AuthTests(TestCase):
    """Registration, login, and login-required screens."""

    def test_register_creates_free_profile_and_lands_in_app(self):
        """A new user is Free and is sent to the workspace."""
        response = self.client.post(
            reverse("accounts:register"),
            {
                "name": "Ada",
                "email": "ada@example.com",
                "password1": "Str0ngPass!word9",
                "password2": "Str0ngPass!word9",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="ada@example.com").exists())
        user = User.objects.get(email="ada@example.com")
        self.assertEqual(user.profile.plan, "free")
        self.assertEqual(response.url, reverse("humanizer:workspace"))

    def test_workspace_requires_login(self):
        """Guests hitting /app/ are sent to login."""
        response = self.client.get(reverse("humanizer:workspace"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_login_and_dashboard(self):
        """Email login reaches the dashboard with weekly quota copy."""
        User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        logged = self.client.login(email="ada@example.com", password="Str0ngPass!word9")
        self.assertTrue(logged)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100,000")

    def test_workspace_renders_split_panes(self):
        """Logged-in users see original and humanized panes."""
        User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        self.client.login(email="ada@example.com", password="Str0ngPass!word9")
        response = self.client.get(reverse("humanizer:workspace"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original")
        self.assertContains(response, "Humanized")


class SecurityTests(TestCase):
    """Hardening rules requested before free PythonAnywhere deployment."""

    def setUp(self):
        # Rate-limit buckets are process-global; isolate aggressive tests.
        from django.core.cache import cache

        cache.clear()

    def test_one_ip_and_device_per_account(self):
        """A second registration from the same IP/device is rejected."""
        self.client.post(
            reverse("accounts:register"),
            {
                "name": "Ada",
                "email": "ada@example.com",
                "password1": "Str0ngPass!word9",
                "password2": "Str0ngPass!word9",
            },
        )
        self.assertEqual(User.objects.count(), 1)

        response = self.client.post(
            reverse("accounts:register"),
            {
                "name": "Bob",
                "email": "bob@example.com",
                "password1": "Str0ngPass!word9",
                "password2": "Str0ngPass!word9",
            },
        )
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already been created from this")

    def test_lockout_escalates_and_records_attempts(self):
        """5 wrong passwords -> 1 min lock, 8 -> 10 min, 9 -> permanent."""
        user = User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        payload = {
            "username": "ada@example.com",
            "password": "wrong",
        }

        for _ in range(5):
            self.client.post(reverse("accounts:login"), payload)

        sp = UserSecurityProfile.objects.get(user=user)
        self.assertEqual(sp.failed_attempts, 5)
        self.assertEqual(sp.lockout_stage, UserSecurityProfile.LOCKOUT_ONE_MINUTE)
        self.assertIsNotNone(sp.locked_until)

        # The 9th wrong attempt triggers a permanent lock.
        for _ in range(4):
            self.client.post(reverse("accounts:login"), payload)

        sp.refresh_from_db()
        self.assertEqual(sp.failed_attempts, 9)
        self.assertEqual(sp.lockout_stage, UserSecurityProfile.LOCKOUT_PERMANENT)
        self.assertTrue(sp.permanently_locked)

        # Audit rows are stored.
        self.assertEqual(
            LoginAttempt.objects.filter(user=user, success=False).count(), 9
        )

    def test_locked_account_cannot_log_in_even_with_correct_password(self):
        """Permanent lockout blocks correct passwords too."""
        user = User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        sp = UserSecurityProfile.objects.get(user=user)
        sp.permanently_locked = True
        sp.save()

        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "ada@example.com",
                "password": "Str0ngPass!word9",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "permanently locked")

    def test_device_binding_blocks_different_device(self):
        """A login from a different user-agent than signup is rejected."""
        # Register from "Chrome" browser (this also logs the client in).
        self.client.post(
            reverse("accounts:register"),
            {
                "name": "Ada",
                "email": "ada@example.com",
                "password1": "Str0ngPass!word9",
                "password2": "Str0ngPass!word9",
            },
            HTTP_USER_AGENT="Mozilla/5.0 Chrome/1.0",
        )
        self.client.logout()

        # Login from "Firefox" fails.
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "ada@example.com",
                "password": "Str0ngPass!word9",
            },
            HTTP_USER_AGENT="Mozilla/5.0 Firefox/1.0",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "locked to the device")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_permanent_lockout_sends_email_to_developer(self):
        """A permanent lock fires an email alert to the developer."""
        from django.core import mail

        user = User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        for _ in range(9):
            self.client.post(
                reverse("accounts:login"),
                {
                    "username": "ada@example.com",
                    "password": "wrong",
                },
            )

        sp = UserSecurityProfile.objects.get(user=user)
        self.assertTrue(sp.permanently_locked)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Account permanently locked", mail.outbox[0].subject)

    def test_successful_login_resets_failed_attempts(self):
        """A good login clears the lockout counter."""
        user = User.objects.create_user(
            email="ada@example.com",
            password="Str0ngPass!word9",
            name="Ada",
        )
        for _ in range(3):
            self.client.post(
                reverse("accounts:login"),
                {
                    "username": "ada@example.com",
                    "password": "wrong",
                },
            )

        self.client.post(
            reverse("accounts:login"),
            {
                "username": "ada@example.com",
                "password": "Str0ngPass!word9",
            },
        )
        sp = UserSecurityProfile.objects.get(user=user)
        self.assertEqual(sp.failed_attempts, 0)
        self.assertEqual(sp.lockout_stage, UserSecurityProfile.LOCKOUT_NONE)
        self.assertTrue(
            LoginAttempt.objects.filter(user=user, success=True).exists()
        )
