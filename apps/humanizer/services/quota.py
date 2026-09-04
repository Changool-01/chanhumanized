"""Weekly word quotas for Free and Pro.

Week starts Monday 00:00 UTC. Failed jobs do not count. Pro's million-word
cap is a fair-use limit and is not shown in the UI.
"""

from datetime import timedelta, timezone as datetime_timezone

from django.conf import settings
from django.utils import timezone

from apps.humanizer.models import RewriteJob
from apps.humanizer.services.wordcount import count_words


def week_start_utc(now=None):
    """Return Monday 00:00 UTC for the week containing `now` (aware datetime)."""
    now = now or timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, datetime_timezone.utc)
    now = timezone.localtime(now, datetime_timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def user_plan(user):
    """Return 'free' or 'pro' from the user's profile (default free)."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return settings.PLAN_FREE
    return profile.plan


def weekly_limit(user):
    """Return the weekly word budget for this user's plan."""
    if user_plan(user) == settings.PLAN_PRO:
        return settings.PRO_WEEKLY_WORD_LIMIT
    return settings.FREE_WEEKLY_WORD_LIMIT


def request_limit(user):
    """Return the per-request word cap for this user's plan."""
    if user_plan(user) == settings.PLAN_PRO:
        return settings.PRO_REQUEST_WORD_LIMIT
    return settings.FREE_REQUEST_WORD_LIMIT


def words_used_this_week(user, now=None):
    """Sum word_count of successful jobs since this week's Monday UTC."""
    start = week_start_utc(now)
    total = (
        RewriteJob.objects.filter(
            user=user,
            status=RewriteJob.STATUS_OK,
            created_at__gte=start,
        ).values_list("word_count", flat=True)
    )
    return sum(total)


def quota_snapshot(user, now=None):
    """
    Build a dict the dashboard and workspace quota bar can render.

    Pro remaining is reported as None so templates can say “Unlimited”
    without exposing the fair-use number.
    """
    plan = user_plan(user)
    used = words_used_this_week(user, now=now)
    limit = weekly_limit(user)
    is_pro = plan == settings.PLAN_PRO
    remaining = None if is_pro else max(0, limit - used)
    return {
        "plan": plan,
        "is_pro": is_pro,
        "used": used,
        "weekly_limit": limit,
        "remaining": remaining,
        "request_limit": request_limit(user),
        "week_start": week_start_utc(now).isoformat(),
    }


class QuotaError(Exception):
    """Raised when a humanize request should not call OpenAI."""

    def __init__(self, code, message):
        """Store a machine code (`over_request` / `over_weekly`) and user text."""
        super().__init__(message)
        self.code = code
        self.message = message


def assert_can_humanize(user, text):
    """
    Raise QuotaError if the text is empty, over the per-request cap,
    or would exceed the weekly budget. Does not debit quota.
    """
    words = count_words(text)
    if words == 0:
        raise QuotaError("empty", "Paste some text to humanize.")
    max_request = request_limit(user)
    if words > max_request:
        raise QuotaError(
            "over_request",
            f"This text is {words} words. Your plan allows {max_request} words per request.",
        )
    used = words_used_this_week(user)
    limit = weekly_limit(user)
    plan = user_plan(user)
    if used + words > limit:
        if plan == settings.PLAN_PRO:
            raise QuotaError(
                "over_weekly",
                "You have reached this week’s writing limit. Please try again next week.",
            )
        remaining = max(0, limit - used)
        raise QuotaError(
            "over_weekly",
            f"This week’s Free quota is {limit:,} words. You have {remaining:,} left. "
            "Upgrade to Pro for a much higher limit.",
        )
    return words
