from __future__ import annotations

from ..glossary.protector import restore_placeholders


def restore_translation_text(text: str, replacements: dict[str, str]) -> str:
    return restore_placeholders(text, replacements)
