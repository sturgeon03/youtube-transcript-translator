from __future__ import annotations

import re


GLOSSARY_PLACEHOLDER_PREFIX = "ZXQTERM"
PROTECTED_TOKEN_PREFIX = "ZXQPROTECT"

PROTECTED_TOKEN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"https?://\S+"),
    re.compile(r"\b[\w./-]+\.(?:py|js|ts|json|xml|txt|csv|md|pdf|png|jpg|mp4|m4a|webm|srt)\b"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\([^)]*\)"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b"),
    re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),
    re.compile(r"[\[\]{}()^_=<>/+*-]{2,}\S*"),
]
