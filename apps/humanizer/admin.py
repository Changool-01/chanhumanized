"""Admin for rewrite history."""

from django.contrib import admin

from apps.humanizer.models import RewriteJob


@admin.register(RewriteJob)
class RewriteJobAdmin(admin.ModelAdmin):
    """Read-mostly list for support; original/result are long so they stay on the detail page."""

    list_display = (
        "id",
        "user",
        "word_count",
        "tone",
        "strength",
        "use_case",
        "domain",
        "status",
        "created_at",
    )
    list_filter = ("status", "tone", "strength", "use_case", "domain", "mode")
    search_fields = ("user__email", "style_note")
    readonly_fields = ("created_at",)
