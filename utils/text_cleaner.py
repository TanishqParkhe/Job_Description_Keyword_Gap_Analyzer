"""Text cleaning helpers for resumes and job descriptions."""

from __future__ import annotations

import html
import re
import unicodedata
from collections import Counter

_ZERO_WIDTH = re.compile(r"[\u200B-\u200D\uFEFF]")
_HTML_TAG = re.compile(r"<[^>]+>")
_BULLET = re.compile(r"^[\s\u2022\u25cf\u25aa\u25e6\u2043\u2219\-*–—]+")


def _remove_repeated_boilerplate(lines: list[str]) -> list[str]:
    normalized = [re.sub(r"\s+", " ", line).strip().lower() for line in lines]
    counts = Counter(item for item in normalized if 3 <= len(item) <= 120)
    return [line for line, key in zip(lines, normalized) if not (counts[key] >= 4 and len(key.split()) <= 14)]


def clean_text(text: object, *, remove_repeated_lines: bool = True) -> str:
    """Return readable normalized text while preserving useful line breaks."""
    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", html.unescape(str(text)))
    value = _ZERO_WIDTH.sub("", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    value = _HTML_TAG.sub(" ", value)
    value = re.sub(r"[\t ]+", " ", value)
    value = re.sub(r"\n[\t ]+", "\n", value)
    lines = [line.strip() for line in value.splitlines()]
    if remove_repeated_lines:
        lines = _remove_repeated_boilerplate(lines)
    cleaned_lines: list[str] = []
    blank = False
    for line in lines:
        if line:
            line = _BULLET.sub("• ", line) if _BULLET.match(line) else line
            cleaned_lines.append(line)
            blank = False
        elif not blank:
            cleaned_lines.append("")
            blank = True
    return "\n".join(cleaned_lines).strip()


def normalize_for_matching(text: object) -> str:
    """Create a lower-case form used only for matching."""
    value = clean_text(text).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9+#./\-\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def split_sentences(text: object) -> list[str]:
    cleaned = clean_text(text)
    chunks = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [item.strip(" •\t") for item in chunks if 3 <= len(item.strip()) <= 600]
