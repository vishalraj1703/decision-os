"""Redaction: emails, phone numbers and long ID numbers are masked before any AI call.

The masked text is what the AI sees and what is stored, so evidence quotes and the
source highlight line up with it. Pattern-based only (no name recognition): names are
kept, because ownership depends on them.
"""

from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# A run of digits with spaces, dashes, dots or brackets between them. Counted below.
NUMBER = re.compile(r"\+?\(?\d[\d \t().-]{7,}\d")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _number(m: re.Match, counts: dict[str, int]) -> str:
    text = m.group(0)
    digits = sum(ch.isdigit() for ch in text)
    if digits < 10 or ISO_DATE.search(text):
        return text
    kind = "phone" if text.startswith("+") or digits <= 12 else "id"
    counts[kind] = counts.get(kind, 0) + 1
    return f"[{kind}]"


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return the masked text and how many of each kind were masked."""
    counts: dict[str, int] = {}

    def email(_: re.Match) -> str:
        counts["email"] = counts.get("email", 0) + 1
        return "[email]"

    out = EMAIL.sub(email, text)
    out = NUMBER.sub(lambda m: _number(m, counts), out)
    return out, counts
