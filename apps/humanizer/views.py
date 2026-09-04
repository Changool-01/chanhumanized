"""Workspace page, history, and the JSON humanize endpoint."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.ratelimit import rate_limit
from apps.humanizer.models import RewriteJob
from apps.humanizer.services.diff import word_diff_html
from apps.humanizer.services.openai import run_humanize_job
from apps.humanizer.services.quota import QuotaError, assert_can_humanize, quota_snapshot
from apps.humanizer.services.wordcount import count_words


def _allowed_choice(value, allowed, default):
    """Return `value` if it is in `allowed`, otherwise `default`."""
    if value in allowed:
        return value
    return default


@login_required
@rate_limit(key="user", rate="60/m", group="workspace")
def workspace(request):
    """Render the split-view humanize screen."""
    snapshot = quota_snapshot(request.user)
    return render(
        request,
        "humanizer/workspace.html",
        {
            "snapshot": snapshot,
            "tones": RewriteJob.TONE_CHOICES,
            "strengths": RewriteJob.STRENGTH_CHOICES,
            "modes": RewriteJob.MODE_CHOICES,
            "use_cases": RewriteJob.USE_CASE_CHOICES,
        },
    )


@login_required
@require_POST
@rate_limit(key="user", rate="30/m", group="humanize")
@rate_limit(key="ip", rate="60/m", group="humanize")
def humanize_api(request):
    """
    JSON: { original_text, tone, strength, mode, use_case, style_note, regenerate } → result.

    Domain is auto-detected from the text in the OpenAI service layer.
    Errors use HTTP 400 with a `code` the frontend can map to a banner.
    Quota is checked before OpenAI is called.
    """
    original = (request.POST.get("original_text") or "").strip()
    tone = _allowed_choice(
        request.POST.get("tone"),
        {c[0] for c in RewriteJob.TONE_CHOICES},
        RewriteJob.TONE_PROFESSIONAL,
    )
    strength = _allowed_choice(
        request.POST.get("strength"),
        {c[0] for c in RewriteJob.STRENGTH_CHOICES},
        RewriteJob.STRENGTH_MEDIUM,
    )
    mode = _allowed_choice(
        request.POST.get("mode"),
        {c[0] for c in RewriteJob.MODE_CHOICES},
        RewriteJob.MODE_PARAGRAPH,
    )
    use_case = _allowed_choice(
        request.POST.get("use_case"),
        {c[0] for c in RewriteJob.USE_CASE_CHOICES},
        RewriteJob.USE_CASE_GENERAL,
    )
    style_note = (request.POST.get("style_note") or "").strip()[:255]
    regenerate = bool(request.POST.get("regenerate"))

    try:
        assert_can_humanize(request.user, original)
    except QuotaError as exc:
        snapshot = quota_snapshot(request.user)
        return JsonResponse(
            {"ok": False, "code": exc.code, "error": exc.message, "snapshot": snapshot},
            status=400,
        )

    job = run_humanize_job(
        request.user,
        original,
        tone,
        strength,
        mode,
        use_case,
        style_note=style_note,
        regenerate=regenerate,
    )
    snapshot = quota_snapshot(request.user)
    if job.status != RewriteJob.STATUS_OK:
        message = job.error_message or "The rewrite failed. Please try again."
        return JsonResponse(
            {"ok": False, "code": "api_error", "error": message, "snapshot": snapshot},
            status=502,
        )

    return JsonResponse(
        {
            "ok": True,
            "humanized_text": job.humanized_text,
            "diff_html": word_diff_html(original, job.humanized_text),
            "word_count": job.word_count,
            "job_id": job.id,
            "snapshot": snapshot,
        }
    )


@login_required
@rate_limit(key="user", rate="60/m", group="history")
def history_list(request):
    """Paginated list of this user's successful rewrites."""
    jobs = RewriteJob.objects.filter(user=request.user, status=RewriteJob.STATUS_OK)
    return render(request, "humanizer/history.html", {"jobs": jobs[:100]})


@login_required
@rate_limit(key="user", rate="60/m", group="history")
def history_detail(request, job_id):
    """Owner-only original vs humanized split view (read-only)."""
    job = get_object_or_404(RewriteJob, pk=job_id, user=request.user)
    return render(
        request,
        "humanizer/history_detail.html",
        {
            "job": job,
            "diff_html": word_diff_html(job.original_text, job.humanized_text),
        },
    )
