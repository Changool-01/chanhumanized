"""Detect whether input reads like a short blurb or a multi-paragraph expository essay."""

from apps.humanizer.services.scoring import avg_sentence_length
from apps.humanizer.services.wordcount import count_words

PROFILE_SHORT = "short"
PROFILE_ESSAY = "essay"


def detect_writing_profile(text):
    """
    Return PROFILE_ESSAY for school-essay / wiki-style multi-paragraph input.

    Short bios, emails, and single paragraphs use the punchier short profile.
    """
    text = (text or "").strip()
    if not text:
        return PROFILE_SHORT

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    words = count_words(text)
    avg_sent = avg_sentence_length(text)

    if len(paragraphs) >= 3:
        return PROFILE_ESSAY
    if words >= 120:
        return PROFILE_ESSAY
    if words >= 80 and avg_sent >= 14:
        return PROFILE_ESSAY
    if len(paragraphs) >= 2 and words >= 70:
        return PROFILE_ESSAY
    return PROFILE_SHORT
