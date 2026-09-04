"""Heuristic scoring for picking the most human-sounding rewrite candidate.

This does not use an AI detector. It measures the same surface patterns the
prompt optimizes for: short uneven sentences, simple words, function words,
repetition, and banned AI phrases. The best candidate is then sent to the
audit pass for final tightening.
"""

import re
from difflib import SequenceMatcher


# Function words that make text feel spoken rather than dense.
FUNCTION_WORDS = {
    "it", "this", "that", "a", "the", "and", "but", "so", "or", "if", "of", "in",
    "on", "for", "with", "to", "at", "by", "as", "i", "you", "we", "he", "she",
    "they", "is", "are", "am", "was", "were", "be", "been", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "can", "may", "might",
    "than", "then", "when", "where", "who", "what", "why", "how", "there", "here",
}

# Phrases that drag a rewrite back toward AI-speak.
BANNED_PHRASES = {
    "with a mix of", "with a strong passion for", "i have developed skills in",
    "connect the dots", "i am a", "i am dedicated", "i have a proven track record",
    "i am highly motivated", "in today's world", "it is important to note",
    "it should be noted", "as a result", "furthermore", "moreover", "ultimately",
    "in conclusion", "needless to say", "delve", "tapestry", "landscape", "multifaceted",
    "pivotal", "robust", "essential tool for", "works well with", "make data easy to",
    "is a go-to tool for", "crucially", "fundamentally", "notably", "significantly",
    "interestingly", "additionally", "consequently", "therefore", "overall",
    "in summary", "in terms of", "with regard to", "in the context of",
    "due to the fact that", "in order to", "designed to", "is used for", "is known for",
    "is regarded as", "is considered to be", "is characterized by", "plays a role",
    "serves as", "acts as", "functions as", "can be used to", "has the ability to",
    "offers a way to", "provides a way to", "makes it easy to", "makes it simple to",
    "helps", "allows", "enables", "assists", "streamlines", "optimizes", "enhances",
    "improves", "facilitates", "dynamic", "smart", "legendary", "crucial", "fundamental",
    "ultimate", "significant", "notable", "versatile", "powerful", "essential", "vital",
    "integral", "paramount", "widespread", "renowned", "famous", "recognized", "acknowledged",
    "worldwide", "universal language", "ignite passion", "unite different people",
    "global phenomenon", "passion and fair play",
}


def _sentences(text):
    """Split text into rough sentences on . ! ? followed by whitespace."""
    raw = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip())]
    return [s for s in raw if s]


def _words(text):
    """Return a list of whitespace-separated tokens."""
    return text.split()


def _sentence_word_counts(text):
    """Return a list of word counts per sentence."""
    return [len(_words(s)) for s in _sentences(text)]


def avg_sentence_length(text):
    """Average number of words per sentence."""
    counts = _sentence_word_counts(text)
    if not counts:
        return 0
    return sum(counts) / len(counts)


def max_sentence_length(text):
    """Longest sentence in words."""
    counts = _sentence_word_counts(text)
    return max(counts) if counts else 0


def very_short_sentence_count(text, threshold=6):
    """Count sentences with fewer than `threshold` words."""
    return sum(1 for c in _sentence_word_counts(text) if c < threshold)


def avg_word_length(text):
    """Average characters per word."""
    words = _words(text)
    if not words:
        return 0
    return sum(len(w) for w in words) / len(words)


def function_word_ratio(text):
    """Fraction of tokens that are common function words."""
    words = _words(text)
    if not words:
        return 0
    return sum(1 for w in words if w.lower().strip(".,!?;:'\"()") in FUNCTION_WORDS) / len(words)


def repetition_ratio(text):
    """
    Return the share of repeated 3-grams in the text.

    Humans naturally repeat phrases; this metric rewards some repetition.
    """
    words = [w.lower().strip(".,!?;:'\"()") for w in _words(text) if w.strip(".,!?;:'\"()")]
    if len(words) < 3:
        return 0
    ngrams = [tuple(words[i : i + 3]) for i in range(len(words) - 2)]
    total = len(ngrams)
    if total == 0:
        return 0
    unique = len(set(ngrams))
    repeated = total - unique
    return repeated / total


def banned_phrase_count(text):
    """Count occurrences of banned AI-speak phrases."""
    lower = text.lower()
    return sum(lower.count(phrase) for phrase in BANNED_PHRASES)


def long_word_ratio(text, threshold=10):
    """Fraction of words longer than `threshold` characters."""
    words = [w.strip(".,!?;:'\"()") for w in _words(text) if w.strip(".,!?;:'\"()")]
    if not words:
        return 0
    return sum(1 for w in words if len(w) > threshold) / len(words)


def similarity(a, b):
    """Return a quick word-level similarity ratio between two texts."""
    return SequenceMatcher(None, a.split(), b.split()).ratio()


def score_candidate(text):
    """
    Return a higher-is-better score for a human-style rewrite candidate.

    The score rewards:
    - short, uneven sentences (average 12-18, max under 20)
    - several very short sentences (< 6 words)
    - short average word length
    - high function-word ratio
    - some natural repetition
    It penalizes banned AI phrases, long words, and sentences that are too long.
    """
    avg_sent = avg_sentence_length(text)
    max_sent = max_sentence_length(text)
    very_short = very_short_sentence_count(text)
    avg_word = avg_word_length(text)
    func_ratio = function_word_ratio(text)
    repeat_ratio = repetition_ratio(text)
    banned = banned_phrase_count(text)
    long_ratio = long_word_ratio(text)
    sentence_count = len(_sentences(text))

    score = 100

    # Target average sentence length ~15 words (midpoint of 12-18).
    score -= abs(avg_sent - 15) * 3

    # Hard cap: no sentence over 20 words.
    if max_sent > 20:
        score -= (max_sent - 20) * 3 + 30

    # Reward punchy 1-5 word sentences.
    score += very_short * 12

    # Prefer a mix where at least half the sentences are under 12 words.
    if sentence_count > 0:
        short_count = sum(1 for c in _sentence_word_counts(text) if c < 12)
        if short_count / sentence_count >= 0.5:
            score += 15
        else:
            score -= 10

    # Short words feel more spoken. Target average ~5.0 characters.
    score -= avg_word * 8
    score -= long_ratio * 60

    # Function words should be around 40-45%.
    score += func_ratio * 150

    # Some repetition is human-like; cap the reward to avoid over-repetition.
    score += min(repeat_ratio, 0.12) * 80

    # Banned AI-speak is heavily penalized.
    score -= banned * 40

    return score


def pick_best_candidate(candidates, original):
    """
    Pick the highest-scoring candidate that is not empty and not identical to
    the original. If none are usable, return the first non-empty candidate.
    """
    scored = []
    for candidate in candidates:
        if not candidate or candidate.strip() == original.strip():
            continue
        scored.append((score_candidate(candidate), candidate))

    if not scored:
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip()
        return original

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1].strip()
