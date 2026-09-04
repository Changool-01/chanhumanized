"""Split long submissions so each OpenAI call stays within a time budget."""

from apps.humanizer.services.wordcount import count_words


def chunk_text(text, max_words):
    """
    Split `text` into chunks of at most `max_words` words.

    Paragraphs (blank-line separated) are kept together when they fit.
    Oversized paragraphs are split on word boundaries. Order is preserved
    so the caller can join chunks with blank lines.
    """
    text = (text or "").strip()
    if not text:
        return []
    if count_words(text) <= max_words:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = []
    current_words = 0

    for para in paragraphs:
        para_words = count_words(para)
        if para_words > max_words:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_words = 0
            chunks.extend(_split_words(para, max_words))
            continue
        if current_words + para_words > max_words and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_words(text, max_words):
    """Split a single oversized block into word-count windows."""
    words = text.split()
    pieces = []
    for i in range(0, len(words), max_words):
        pieces.append(" ".join(words[i : i + max_words]))
    return pieces
