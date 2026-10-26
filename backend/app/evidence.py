"""Evidence verification: a quote counts only if it really appears in the notes.

The spec only asks for a non-empty evidence_quote; that alone would let a model invent a
sentence and pass. Here every quote is located in the stored notes and its character
range is recorded, which is what the "view source" highlight uses.
"""

from __future__ import annotations

import re

_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercased, quote-folded, whitespace-collapsed text plus a map back to original offsets."""
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(text.translate(_FOLD)):
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        idx.append(i)
    return "".join(out), idx


def locate(quote: str, notes: str) -> tuple[int, int] | None:
    """Return (start, end) character offsets of `quote` inside `notes`, or None."""
    if not quote or not quote.strip():
        return None
    q, _ = _norm_with_map(quote.strip())
    q = q.strip().strip("\"'")
    n, idx = _norm_with_map(notes)
    for candidate in (q, q.rstrip(".!?;,")):
        if len(candidate) < 6:
            continue
        pos = n.find(candidate)
        if pos >= 0:
            start = idx[pos]
            end = idx[pos + len(candidate) - 1] + 1
            return start, end
    return None


def sentence_around(notes: str, start: int, end: int) -> tuple[int, int]:
    """Expand a span to the full sentence containing it (for display)."""
    left = max(notes.rfind(".", 0, start), notes.rfind("\n", 0, start), notes.rfind("!", 0, start), notes.rfind("?", 0, start))
    s = left + 1 if left >= 0 else 0
    rights = [p for p in (notes.find(".", end), notes.find("\n", end), notes.find("!", end), notes.find("?", end)) if p >= 0]
    e = min(rights) + 1 if rights else len(notes)
    while s < e and notes[s].isspace():
        s += 1
    return s, min(e, len(notes))


def word_in(word: str, text: str) -> bool:
    if not word:
        return False
    return re.search(r"\b" + re.escape(word.strip()) + r"\b", text, re.I) is not None
