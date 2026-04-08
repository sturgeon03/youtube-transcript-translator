from __future__ import annotations

import re

from .rules import GLOSSARY_PLACEHOLDER_PREFIX, PROTECTED_TOKEN_PATTERNS, PROTECTED_TOKEN_PREFIX


def glossary_entries_by_priority(glossary: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(glossary.items(), key=lambda item: (-len(item[0]), item[0].lower()))


def glossary_pattern(source: str) -> re.Pattern[str]:
    if re.fullmatch(r"[A-Za-z0-9]+(?:[ .+-][A-Za-z0-9]+)*", source):
        return re.compile(rf"\b{re.escape(source)}\b", re.IGNORECASE)
    return re.compile(re.escape(source), re.IGNORECASE)


def mask_protected_tokens(text: str) -> tuple[str, dict[str, str]]:
    masked_text = text
    replacements: dict[str, str] = {}
    placeholder_index = 0

    for pattern in PROTECTED_TOKEN_PATTERNS:

        def replacer(match: re.Match[str]) -> str:
            nonlocal placeholder_index
            token = match.group(0)
            placeholder = f"{PROTECTED_TOKEN_PREFIX}{placeholder_index}ZXQ"
            placeholder_index += 1
            replacements[placeholder] = token
            return placeholder

        masked_text = pattern.sub(replacer, masked_text)

    return masked_text, replacements


def mask_glossary_terms(text: str, glossary: dict[str, str]) -> tuple[str, dict[str, str]]:
    if not glossary:
        return text, {}

    masked_text = text
    replacements: dict[str, str] = {}
    placeholder_index = 0

    for source, target in glossary_entries_by_priority(glossary):
        pattern = glossary_pattern(source)

        def replacer(match: re.Match[str]) -> str:
            nonlocal placeholder_index
            placeholder = f"{GLOSSARY_PLACEHOLDER_PREFIX}{placeholder_index}ZXQ"
            placeholder_index += 1
            replacements[placeholder] = target
            return placeholder

        masked_text = pattern.sub(replacer, masked_text)

    return masked_text, replacements


def restore_placeholders(text: str, replacements: dict[str, str]) -> str:
    restored = text
    for placeholder, target in replacements.items():
        restored = restored.replace(placeholder, target)
    return restored


def prepare_text_for_translation(text: str, glossary: dict[str, str]) -> tuple[str, dict[str, str]]:
    masked_text, protected_replacements = mask_protected_tokens(text)
    masked_text, glossary_replacements = mask_glossary_terms(masked_text, glossary)
    replacements = {**protected_replacements, **glossary_replacements}
    return masked_text, replacements
