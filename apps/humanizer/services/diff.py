"""Word-level diff highlighting for the humanize workspace.

Shows which words were removed and which were added. The output is HTML
with <span> wrappers; the caller must already escape the text before
rendering it (Django templates do that by default). Diff is computed server
side so the UI does not need to ship a diff library.
"""

import html
from difflib import SequenceMatcher


def word_diff_html(original, rewritten):
    """
    Return an HTML string showing the rewrite with word-level highlights.

    Added words are wrapped in <span class="diff-ins">; removed words are
    wrapped in <span class="diff-del">. Words that are unchanged are plain
    text. Punctuation stays attached to the word it touches. The result is
    safe for insertion into a <pre> element because all words are escaped.

    Args:
        original: The user's original text.
        rewritten: The humanized text.

    Returns:
        HTML string, or an empty string if either input is blank.
    """
    if not original or not rewritten:
        return ""

    a = str(original).split()
    b = str(rewritten).split()
    matcher = SequenceMatcher(None, a, b)
    parts = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append(" ".join(html.escape(w) for w in a[i1:i2]))
        elif tag == "delete":
            chunk = " ".join(html.escape(w) for w in a[i1:i2])
            parts.append(f'<span class="diff-del">{chunk}</span>')
        elif tag == "insert":
            chunk = " ".join(html.escape(w) for w in b[j1:j2])
            parts.append(f'<span class="diff-ins">{chunk}</span>')
        elif tag == "replace":
            deleted = " ".join(html.escape(w) for w in a[i1:i2])
            inserted = " ".join(html.escape(w) for w in b[j1:j2])
            parts.append(f'<span class="diff-del">{deleted}</span>')
            parts.append(f'<span class="diff-ins">{inserted}</span>')

    return " ".join(parts)
