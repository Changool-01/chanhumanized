"""Humanizer tests: word count, chunks, quota, OpenAI service, JSON API, diff, scoring, domain detection."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.humanizer.models import RewriteJob
from apps.humanizer.services.chunking import chunk_text
from apps.humanizer.services.diff import word_diff_html
from apps.humanizer.services.openai import detect_domain
from apps.humanizer.services.quota import QuotaError, assert_can_humanize, words_used_this_week
from apps.humanizer.services.scoring import pick_best_candidate, score_candidate
from apps.humanizer.services.wordcount import count_words


class WordCountTests(TestCase):
    """Keep Python counting aligned with the JS counter rules."""

    def test_empty_is_zero(self):
        """Blank text is zero words."""
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("   "), 0)

    def test_splits_on_whitespace(self):
        """Multiple spaces still count as separate tokens only when non-empty."""
        self.assertEqual(count_words("one two three"), 3)


class ChunkingTests(TestCase):
    """Long text is split so OpenAI calls stay small."""

    def test_short_text_is_one_chunk(self):
        """A short paragraph is not split."""
        self.assertEqual(chunk_text("hello there", 10), ["hello there"])

    def test_splits_oversized_paragraph(self):
        """A single long paragraph is cut on word boundaries."""
        text = " ".join(["word"] * 25)
        chunks = chunk_text(text, 10)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(count_words(chunks[0]), 10)


class DiffTests(TestCase):
    """Diff highlighting marks additions and removals."""

    def test_equal_text_has_no_highlights(self):
        """Identical strings produce plain escaped text."""
        html = word_diff_html("hello world", "hello world")
        self.assertIn("hello", html)
        self.assertNotIn("diff-ins", html)
        self.assertNotIn("diff-del", html)

    def test_insertion_and_deletion(self):
        """Changed words get span wrappers."""
        html = word_diff_html("the quick cat", "the fast cat")
        self.assertIn('<span class="diff-del">quick</span>', html)
        self.assertIn('<span class="diff-ins">fast</span>', html)

    def test_escapes_html(self):
        """HTML metacharacters in input are escaped."""
        html = word_diff_html("<b>bold</b>", "<i>italic</i>")
        self.assertNotIn("<b>bold</b>", html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html)


class QuotaTests(TestCase):
    """Per-request and weekly caps block OpenAI when exceeded."""

    def setUp(self):
        """Create a Free user for quota checks."""
        self.user = User.objects.create_user(
            email="free@example.com",
            password="Str0ngPass!word9",
            name="Free User",
        )

    def test_rejects_over_request_limit(self):
        """More than 2,000 words on Free raises over_request."""
        text = " ".join(["word"] * 2001)
        with self.assertRaises(QuotaError) as ctx:
            assert_can_humanize(self.user, text)
        self.assertEqual(ctx.exception.code, "over_request")

    def test_failed_jobs_do_not_count(self):
        """Only successful jobs add to the weekly total."""
        RewriteJob.objects.create(
            user=self.user,
            original_text="hello",
            word_count=400,
            status=RewriteJob.STATUS_FAILED,
        )
        self.assertEqual(words_used_this_week(self.user), 0)


class DetectDomainTests(TestCase):
    """Auto-detect the writing domain from keywords."""

    def test_empty_short_text_is_general(self):
        """Empty or very short input falls back to general."""
        self.assertEqual(detect_domain(""), RewriteJob.DOMAIN_GENERAL)
        self.assertEqual(detect_domain("hi"), RewriteJob.DOMAIN_GENERAL)

    def test_detects_sports(self):
        """Football and soccer keywords resolve to sports."""
        self.assertEqual(detect_domain("Football is a global sport with leagues and FIFA."), RewriteJob.DOMAIN_SPORTS)

    def test_detects_coding(self):
        """Python and Django keywords resolve to coding."""
        self.assertEqual(detect_domain("Python and Django are used for web development."), RewriteJob.DOMAIN_CODING)

    def test_detects_finance(self):
        """Stock, market, and profit keywords resolve to finance."""
        self.assertEqual(detect_domain("The stock market delivered strong profit this quarter."), RewriteJob.DOMAIN_FINANCE)

    def test_detects_business(self):
        """Company and team keywords resolve to business."""
        self.assertEqual(detect_domain("Our company needs a better team strategy."), RewriteJob.DOMAIN_BUSINESS)

    def test_generic_text_is_general(self):
        """Text with no domain keywords stays general."""
        self.assertEqual(detect_domain("This is a short sample."), RewriteJob.DOMAIN_GENERAL)


class HumanizeApiTests(TestCase):
    """JSON endpoint: login, quota errors, mocked success, ownership, use_case, auto-detected domain."""

    def setUp(self):
        """Log in a Free user."""
        self.user = User.objects.create_user(
            email="writer@example.com",
            password="Str0ngPass!word9",
            name="Writer",
        )
        self.client.login(email="writer@example.com", password="Str0ngPass!word9")

    def test_empty_text_is_400(self):
        """Empty paste returns a JSON error and does not create an OK job."""
        response = self.client.post(reverse("humanizer:humanize_api"), {"original_text": ""})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_over_request_is_400(self):
        """Over-limit paste is rejected before OpenAI."""
        text = " ".join(["word"] * 2001)
        response = self.client.post(
            reverse("humanizer:humanize_api"),
            {
                "original_text": text,
                "tone": "academic",
                "strength": "medium",
                "mode": "paragraph",
                "use_case": "email",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "over_request")

    @override_settings(OPENAI_API_KEY="")
    def test_missing_api_key_is_502(self):
        """Without a key, the job fails and quota is not charged."""
        response = self.client.post(
            reverse("humanizer:humanize_api"),
            {
                "original_text": "This is a short sample.",
                "tone": "professional",
                "strength": "medium",
                "mode": "paragraph",
                "use_case": "email",
            },
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(RewriteJob.objects.filter(status=RewriteJob.STATUS_OK).count(), 0)

    @patch(
        "apps.humanizer.services.openai.humanize_text",
        return_value=("A more natural sentence.", "gpt-4o-mini"),
    )
    def test_success_saves_job_and_counts_words(self, _mock):
        """A mocked rewrite stores history and returns JSON with diff."""
        response = self.client.post(
            reverse("humanizer:humanize_api"),
            {
                "original_text": "This is a short sample.",
                "tone": "professional",
                "strength": "medium",
                "mode": "paragraph",
                "use_case": "email",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["humanized_text"], "A more natural sentence.")
        self.assertIn("diff-ins", payload["diff_html"])
        job = RewriteJob.objects.get()
        self.assertEqual(job.status, RewriteJob.STATUS_OK)
        self.assertEqual(job.word_count, 5)
        self.assertEqual(job.use_case, "email")
        self.assertEqual(job.domain, RewriteJob.DOMAIN_GENERAL)
        self.assertEqual(job.style_note, "")

    @patch(
        "apps.humanizer.services.openai.humanize_text",
        return_value=("A sports version.", "gpt-4o-mini"),
    )
    def test_style_note_saved_and_domain_auto_detected(self, _mock):
        """Domain is inferred from the text and style_note is saved."""
        response = self.client.post(
            reverse("humanizer:humanize_api"),
            {
                "original_text": "Football is a global sport.",
                "tone": "casual",
                "strength": "medium",
                "mode": "paragraph",
                "use_case": "general",
                "style_note": "write like a Reddit comment",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        job = RewriteJob.objects.get()
        self.assertEqual(job.domain, "sports")
        self.assertEqual(job.style_note, "write like a Reddit comment")
        # Confirm the auto-detected domain was passed to the service
        _mock.assert_called_once()
        args = _mock.call_args.args
        self.assertEqual(args[5], "sports")
        self.assertEqual(args[6], "write like a Reddit comment")

    def test_history_is_owner_only(self):
        """Another user cannot open someone else's rewrite."""
        job = RewriteJob.objects.create(
            user=self.user,
            original_text="mine",
            humanized_text="yours",
            word_count=1,
            status=RewriteJob.STATUS_OK,
        )
        stranger = User.objects.create_user(
            email="other@example.com",
            password="Str0ngPass!word9",
            name="Other",
        )
        self.client.login(email="other@example.com", password="Str0ngPass!word9")
        response = self.client.get(reverse("humanizer:history_detail", args=[job.pk]))
        self.assertEqual(response.status_code, 404)
        # silence unused warning if login returns bool
        self.assertTrue(stranger.pk)


class ScoringTests(TestCase):
    """Local heuristic scorer picks the more human-sounding candidate."""

    def test_short_choppy_scores_higher_than_dense(self):
        """A short, uneven candidate scores higher than a dense one."""
        choppy = "Python is easy. Beginners like it. Experts use it too."
        dense = "Python is a high-level, general-purpose programming language celebrated for its readability and widespread adoption by both novices and seasoned professionals."
        self.assertGreater(score_candidate(choppy), score_candidate(dense))

    def test_pick_best_prefers_choppy(self):
        """pick_best_candidate returns the choppier candidate, not the original."""
        original = "Python is a high-level programming language known for its readability."
        dense = "Python is a high-level, general-purpose programming language celebrated for its readability and simplicity."
        choppy = "Python is a high-level language. It's easy to read."
        best = pick_best_candidate([dense, choppy], original)
        self.assertEqual(best, choppy)

    def test_domain_banned_helpers_are_nonempty(self):
        """Domain hint and banned-phrase helpers cover the new domains."""
        from apps.humanizer.services.openai import DOMAIN_HINTS, DOMAIN_BANNED
        self.assertIn(RewriteJob.DOMAIN_SPORTS, DOMAIN_HINTS)
        self.assertIn(RewriteJob.DOMAIN_SPORTS, DOMAIN_BANNED)
        self.assertTrue(DOMAIN_BANNED[RewriteJob.DOMAIN_SPORTS])
