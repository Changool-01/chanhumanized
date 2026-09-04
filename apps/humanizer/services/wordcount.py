"""Word counting used by both quota checks and the JSON API.

Must stay in sync with static/js/wordcount.js (whitespace-separated tokens).
"""


def count_words(text):
    """
    Return the number of whitespace-separated tokens in `text`.

    Empty or whitespace-only strings count as zero. This matches the
    live counter in the workspace so the UI and server never disagree.
    """
    if not text or not str(text).strip():
        return 0
    return len(str(text).split())
