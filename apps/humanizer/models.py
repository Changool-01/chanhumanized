"""RewriteJob: one stored humanize run per successful (or failed) request."""

from django.conf import settings
from django.db import models


class RewriteJob(models.Model):
    """A single humanize run: original text, result, options, and word count."""

    MODE_SENTENCE = "sentence"
    MODE_PARAGRAPH = "paragraph"
    MODE_CHOICES = (
        (MODE_SENTENCE, "Sentence"),
        (MODE_PARAGRAPH, "Paragraph"),
    )

    TONE_CASUAL = "casual"
    TONE_CONVERSATIONAL = "conversational"
    TONE_PROFESSIONAL = "professional"
    TONE_ACADEMIC = "academic"
    TONE_CHOICES = (
        (TONE_CASUAL, "Casual"),
        (TONE_CONVERSATIONAL, "Conversational"),
        (TONE_PROFESSIONAL, "Professional"),
        (TONE_ACADEMIC, "Academic"),
    )

    STRENGTH_LIGHT = "light"
    STRENGTH_MEDIUM = "medium"
    STRENGTH_HEAVY = "heavy"
    STRENGTH_CHOICES = (
        (STRENGTH_LIGHT, "Light"),
        (STRENGTH_MEDIUM, "Medium"),
        (STRENGTH_HEAVY, "Heavy"),
    )

    USE_CASE_GENERAL = "general"
    USE_CASE_EMAIL = "email"
    USE_CASE_LINKEDIN = "linkedin"
    USE_CASE_REPORT = "report"
    USE_CASE_COVER_LETTER = "cover_letter"
    USE_CASE_MESSAGE = "message"
    USE_CASE_CHOICES = (
        (USE_CASE_GENERAL, "General"),
        (USE_CASE_EMAIL, "Email"),
        (USE_CASE_LINKEDIN, "LinkedIn / Post"),
        (USE_CASE_REPORT, "Report"),
        (USE_CASE_COVER_LETTER, "Cover letter"),
        (USE_CASE_MESSAGE, "Slack / Message"),
    )

    DOMAIN_GENERAL = "general"
    DOMAIN_CODING = "coding"
    DOMAIN_FINANCE = "finance"
    DOMAIN_BUSINESS = "business"
    DOMAIN_EDUCATION = "education"
    DOMAIN_SPORTS = "sports"
    DOMAIN_POLITICS = "politics"
    DOMAIN_HEALTHCARE = "healthcare"
    DOMAIN_CREATIVE = "creative"
    DOMAIN_MARKETING = "marketing"
    DOMAIN_CHOICES = (
        (DOMAIN_GENERAL, "General"),
        (DOMAIN_CODING, "Coding / Tech"),
        (DOMAIN_FINANCE, "Finance"),
        (DOMAIN_BUSINESS, "Business"),
        (DOMAIN_EDUCATION, "Education"),
        (DOMAIN_SPORTS, "Sports"),
        (DOMAIN_POLITICS, "Politics"),
        (DOMAIN_HEALTHCARE, "Healthcare"),
        (DOMAIN_CREATIVE, "Creative"),
        (DOMAIN_MARKETING, "Marketing"),
    )

    STATUS_OK = "ok"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_OK, "OK"),
        (STATUS_FAILED, "Failed"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rewrite_jobs",
    )
    original_text = models.TextField()
    humanized_text = models.TextField(blank=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_PARAGRAPH)
    tone = models.CharField(max_length=32, choices=TONE_CHOICES, default=TONE_PROFESSIONAL)
    strength = models.CharField(
        max_length=16, choices=STRENGTH_CHOICES, default=STRENGTH_MEDIUM
    )
    use_case = models.CharField(
        max_length=32, choices=USE_CASE_CHOICES, default=USE_CASE_GENERAL
    )
    domain = models.CharField(
        max_length=32, choices=DOMAIN_CHOICES, default=DOMAIN_GENERAL
    )
    style_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional one-line style note, e.g. 'write like a Reddit comment'.",
    )
    word_count = models.PositiveIntegerField(default=0)
    model_name = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OK)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        """Short label for admin and history lists."""
        return f"{self.user} · {self.word_count} words · {self.created_at:%Y-%m-%d}"

    def snippet(self, length=80):
        """First `length` characters of the original, for history rows."""
        text = " ".join(self.original_text.split())
        if len(text) <= length:
            return text
        return text[: length - 1] + "…"
