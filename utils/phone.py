"""Phone-related helpers."""

from __future__ import annotations

import re

__all__ = ["normalize_phone"]

_phone_digits_re = re.compile(r"[^\d+]")


def normalize_phone(s: str) -> str:
    """Normalize phone numbers to unified international-like format."""
    s = (s or "").strip()
    s = _phone_digits_re.sub("", s)

    # Russian numbers normalization
    if s.startswith("8") and len(s) == 11:
        s = "+7" + s[1:]
    elif s.startswith("7") and len(s) == 11:
        s = "+" + s
    elif len(s) == 10 and s.isdigit():
        s = "+7" + s

    if not s.startswith("+") and s:
        s = "+" + s

    return s
