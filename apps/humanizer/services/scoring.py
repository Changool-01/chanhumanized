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
    # Encyclopedic / school-essay AI patterns (common in ZeroGPT flags).
    "also known as", "team sport", "objective is to", "objective is", "throughout history",
    "dates back to", "dates back", "rectangular field", "spherical ball", "played between",
    "very popular", "widely regarded", "widely considered", "widely used", "widely known",
    "millions of people", "millions of fans", "attracts millions", "contributes significantly",
    "plays a vital role", "plays an important role", "rich history", "in ancient times",
    "ever since then", "throughout the world", "across the globe", "on a global scale",
    "it is believed", "it is considered", "it is estimated", "it is one of the",
    "one of the most", "some of the most", "known for its", "famous for its",
    "in addition to", "as well as", "such as", "including but not limited",
    "whether you are", "whether you're", "not only", "but also",
    "four billion", "billion fans", "long history", "many experts believe",
    "experts believe", "brings people together", "anyone can learn",
    "simple rules that", "two of the biggest", "biggest events in sports",
    "with great passion", "every season", "football is very popular",
    "the game has simple", "today, football",
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


def _consecutive_very_short(text, threshold=6):
    """Count the number of very short sentences that appear back-to-back."""
    counts = _sentence_word_counts(text)
    runs = 0
    current_run = 0
    for c in counts:
        if c < threshold:
            current_run += 1
        else:
            if current_run > 1:
                runs += current_run
            current_run = 0
    if current_run > 1:
        runs += current_run
    return runs


def sentence_length_std(text):
    """Standard deviation of sentence word counts; higher means more variation."""
    counts = _sentence_word_counts(text)
    if len(counts) < 2:
        return 0
    mean = sum(counts) / len(counts)
    variance = sum((c - mean) ** 2 for c in counts) / len(counts)
    return variance ** 0.5


def sentence_starter_diversity(text):
    """Count unique first words across sentences. Humans vary starters more than AI text."""
    sentences = _sentences(text)
    if not sentences:
        return 0
    starters = set()
    for s in sentences:
        words = _words(s)
        if words:
            first = words[0].lower().strip(".,!?;:'\"")
            if first:
                starters.add(first)
    return len(starters)


def templated_opener_count(text):
    """Count sentences that open like Wikipedia or templated AI essays."""
    patterns = (
        r"^(it|there|this|that|these|those|one|many|most|some|football|the game|the sport)\s+"
        r"(is|are|was|were|has|have|can|will)\b",
        r"^(in|throughout|during)\s+(the|ancient|modern)\b",
    )
    count = 0
    for sentence in _sentences(text):
        lower = sentence.lower()
        for pattern in patterns:
            if re.match(pattern, lower):
                count += 1
                break
    return count


def _score_short_profile(text, original=None):
    """
    Score punchy rewrites (bios, emails, single paragraphs).

    Rewards short uneven sentences; penalizes choppy fragment runs.
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
    choppy_runs = _consecutive_very_short(text)
    burstiness = sentence_length_std(text)
    starter_diversity = sentence_starter_diversity(text)

    score = 100

    # Target average sentence length ~13 words (midpoint of 10-16).
    score -= abs(avg_sent - 13) * 3

    # Hard cap: no sentence over 22 words.
    if max_sent > 22:
        score -= (max_sent - 22) * 4 + 25

    # Reward punchy 1-5 word sentences, but cap the reward so the model
    # does not turn the text into an unreadable fragment list.
    score += min(very_short, 4) * 10

    # Prefer a mix where at least half the sentences are under 12 words.
    if sentence_count > 0:
        short_count = sum(1 for c in _sentence_word_counts(text) if c < 12)
        short_ratio = short_count / sentence_count
        if short_ratio >= 0.5:
            score += 18
        else:
            score -= 12

    # Penalize back-to-back very short sentences so the output does not
    # turn into a staccato fragment list.
    score -= choppy_runs * 5

    # Reward natural burstiness, but not so much that the model ignores the
    # short-sentence target. A healthy std dev for this domain is 4-8 words.
    score += min(burstiness, 8) * 2

    # Reward varied sentence starters. Humans rarely open every sentence the same way.
    score += min(starter_diversity, 6) * 3

    # Short words feel more spoken. Target average ~5.0 characters.
    score -= avg_word * 8
    score -= long_ratio * 60

    # Function words should be around 40-45%.
    score += func_ratio * 150

    # Some repetition is human-like; cap the reward to avoid over-repetition.
    score += min(repeat_ratio, 0.12) * 80

    # Banned AI-speak is heavily penalized.
    score -= banned * 40

    # Flat rhythm (every sentence similar length) reads machine-made to detectors.
    if burstiness < 3.5:
        score -= 22

    # Wikipedia-style openers.
    score -= templated_opener_count(text) * 12

    # Keep facts but break the original's sentence skeleton.
    if original:
        sim = similarity(text, original)
        if sim > 0.68:
            score -= (sim - 0.68) * 180

    return score


def _score_essay_profile(text, original=None):
    """
    Score multi-paragraph expository rewrites.

    Favors flowing prose with varied rhythm — not SMS-style fragments.
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
    choppy_runs = _consecutive_very_short(text)
    burstiness = sentence_length_std(text)
    starter_diversity = sentence_starter_diversity(text)

    score = 100

    # Flowing student essay: average ~15–19 words, not telegraphic.
    score -= abs(avg_sent - 17) * 2.5

    if max_sent > 32:
        score -= (max_sent - 32) * 3 + 15

    score += min(very_short, 2) * 6
    score -= choppy_runs * 8

    if sentence_count > 0:
        short_count = sum(1 for c in _sentence_word_counts(text) if c < 12)
        short_ratio = short_count / sentence_count
        if 0.2 <= short_ratio <= 0.45:
            score += 15
        elif short_ratio > 0.55:
            score -= 20

    score += min(burstiness, 10) * 2.5
    score += min(starter_diversity, 8) * 4
    score -= avg_word * 5
    score -= long_ratio * 40
    score += func_ratio * 70
    score += min(repeat_ratio, 0.1) * 50
    score -= banned * 55
    if burstiness < 4:
        score -= 18
    score -= templated_opener_count(text) * 18

    if original:
        sim = similarity(text, original)
        if sim > 0.72:
            score -= (sim - 0.72) * 200

    return score


def score_candidate(text, original=None, profile="short"):
    """Return a higher-is-better score; profile is ``short`` or ``essay``."""
    if profile == "essay":
        return _score_essay_profile(text, original=original)
    return _score_short_profile(text, original=original)


def pick_best_candidate(candidates, original, profile="short"):
    """
    Pick the highest-scoring candidate that is not empty and not identical to
    the original. If none are usable, return the first non-empty candidate.
    """
    scored = []
    for candidate in candidates:
        if not candidate or candidate.strip() == original.strip():
            continue
        scored.append((score_candidate(candidate, original=original, profile=profile), candidate))

    if not scored:
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip()
        return original

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1].strip()
