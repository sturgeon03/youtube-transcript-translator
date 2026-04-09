from __future__ import annotations

import re
from dataclasses import dataclass

from ..glossary.protector import glossary_pattern
from ..glossary.rules import PROTECTED_TOKEN_PATTERNS
from ..normalize.regroup import wrapped_lines
from ..normalize.text_cleaner import normalize_text
from ..transcript.models import TranscriptSegment


@dataclass(frozen=True)
class QualityIssue:
    segment_index: int
    category: str
    message: str


def find_overlong_segments(
    segments: list[TranscriptSegment],
    *,
    wrap_width: int,
    max_lines: int = 2,
) -> list[TranscriptSegment]:
    flagged = []
    for segment in segments:
        if len(wrapped_lines(segment.text, wrap_width)) > max_lines:
            flagged.append(segment)
    return flagged


def extract_protected_tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    tokens: list[str] = []
    seen: set[str] = set()
    for pattern in PROTECTED_TOKEN_PATTERNS:
        for match in pattern.finditer(normalized):
            token = match.group(0).strip()
            if token and token not in seen:
                tokens.append(token)
                seen.add(token)
    return tokens


def find_missing_protected_tokens(
    english_segments: list[TranscriptSegment],
    translated_segments: list[TranscriptSegment],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for english, translated in zip(english_segments, translated_segments):
        for token in extract_protected_tokens(english.text):
            if token not in translated.text:
                issues.append(
                    QualityIssue(
                        segment_index=english.index,
                        category="protected_token",
                        message=f"Missing protected token in translation: {token}",
                    )
                )
    return issues


def find_missing_glossary_targets(
    english_segments: list[TranscriptSegment],
    translated_segments: list[TranscriptSegment],
    glossary: dict[str, str],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    lowered_cache: dict[int, str] = {}

    for english, translated in zip(english_segments, translated_segments):
        lowered_translation = lowered_cache.setdefault(translated.index, translated.text.lower())
        for source, target in glossary.items():
            if glossary_pattern(source).search(english.text) and target.lower() not in lowered_translation:
                issues.append(
                    QualityIssue(
                        segment_index=english.index,
                        category="glossary_target",
                        message=f"Glossary target missing for '{source}' -> '{target}'",
                    )
                )
    return issues


def find_repeated_term_inconsistencies(
    english_segments: list[TranscriptSegment],
    translated_segments: list[TranscriptSegment],
    glossary: dict[str, str],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []

    for source, target in glossary.items():
        matching_indices = [
            english.index
            for english in english_segments
            if glossary_pattern(source).search(english.text)
        ]
        if len(matching_indices) < 2:
            continue

        missing_indices = []
        for english, translated in zip(english_segments, translated_segments):
            if english.index not in matching_indices:
                continue
            if target.lower() not in translated.text.lower():
                missing_indices.append(english.index)

        if missing_indices:
            issues.append(
                QualityIssue(
                    segment_index=missing_indices[0],
                    category="term_consistency",
                    message=(
                        f"Repeated glossary term '{source}' is not rendered consistently as '{target}' "
                        f"in segments {', '.join(str(index) for index in missing_indices)}"
                    ),
                )
            )
    return issues


def find_symbol_preservation_issues(
    english_segments: list[TranscriptSegment],
    translated_segments: list[TranscriptSegment],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    symbol_pattern = re.compile(r"[=+\-*/^<>_{}\[\]()]")

    for english, translated in zip(english_segments, translated_segments):
        source_symbols = [symbol for symbol in symbol_pattern.findall(english.text)]
        if not source_symbols:
            continue
        translated_symbols = translated.text
        for symbol in set(source_symbols):
            if symbol not in translated_symbols:
                issues.append(
                    QualityIssue(
                        segment_index=english.index,
                        category="symbol_preservation",
                        message=f"Symbol or equation marker missing in translation: {symbol}",
                    )
                )
    return issues


def collect_translation_quality_issues(
    english_segments: list[TranscriptSegment],
    translated_segments: list[TranscriptSegment],
    *,
    glossary: dict[str, str],
    wrap_width: int,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    issues.extend(find_missing_protected_tokens(english_segments, translated_segments))
    issues.extend(find_missing_glossary_targets(english_segments, translated_segments, glossary))
    issues.extend(find_repeated_term_inconsistencies(english_segments, translated_segments, glossary))
    issues.extend(find_symbol_preservation_issues(english_segments, translated_segments))
    issues.extend(
        QualityIssue(
            segment_index=segment.index,
            category="display_length",
            message="Rendered subtitle would exceed the configured display line limit.",
        )
        for segment in find_overlong_segments(translated_segments, wrap_width=wrap_width)
    )
    return issues
