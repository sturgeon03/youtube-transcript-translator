from __future__ import annotations

import re
import time

from deep_translator import GoogleTranslator

from ..glossary.protector import prepare_text_for_translation
from ..normalize.regroup import build_display_friendly_subtitles, merge_text_segments
from ..normalize.text_cleaner import normalize_text, words
from ..postprocess.restore import restore_translation_text
from ..transcript.models import TranscriptSegment
from .base import TranslationBackend


def split_text_for_translation(text: str) -> list[str]:
    split_patterns = [
        r"(?<=[.!?])\s+",
        r"(?<=[,;:])\s+",
        r"(?<=\))\s+",
    ]

    for pattern in split_patterns:
        parts = [part.strip() for part in re.split(pattern, text) if part.strip()]
        if len(parts) > 1:
            return merge_text_segments(parts)

    word_parts = words(text)
    if len(word_parts) > 6:
        midpoint = len(word_parts) // 2
        return [
            " ".join(word_parts[:midpoint]).strip(),
            " ".join(word_parts[midpoint:]).strip(),
        ]

    midpoint = len(text) // 2
    split_at = text.rfind(" ", 0, midpoint)
    if split_at == -1:
        split_at = text.find(" ", midpoint)
    if split_at == -1:
        return [text]
    return [text[:split_at].strip(), text[split_at:].strip()]


def translate_text_google(translator: GoogleTranslator, text: str, depth: int = 0) -> str:
    clean_text = normalize_text(text)
    if not clean_text:
        return ""

    try:
        translated = translator.translate(clean_text)
        if translated is None:
            raise ValueError("Translator returned no text.")
        translated = translated.strip()
        if not translated:
            raise ValueError("Translator returned an empty string.")
        return translated
    except Exception:
        if depth >= 4:
            raise

        parts = split_text_for_translation(clean_text)
        if len(parts) <= 1:
            raise

        translated_parts = []
        for part in parts:
            translated_parts.append(translate_text_google(translator, part, depth + 1))
            time.sleep(0.2)
        return " ".join(part.strip() for part in translated_parts if part.strip())


def translate_batch_google(translator: GoogleTranslator, texts: list[str]) -> list[str]:
    try:
        return translator.translate_batch(texts)
    except Exception:
        translated = []
        for text in texts:
            translated.append(translate_text_google(translator, text))
            time.sleep(0.2)
        return translated


class GoogleTranslationBackend(TranslationBackend):
    name = "google"

    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        wrap_width: int,
        batch_size: int,
        glossary: dict[str, str],
    ) -> list[TranscriptSegment]:
        translator = GoogleTranslator(source="en", target="ko")
        translated: list[TranscriptSegment] = []
        next_index = 1

        for offset in range(0, len(segments), batch_size):
            batch = segments[offset : offset + batch_size]
            prepared_texts = []
            replacements_per_text = []
            for segment in batch:
                prepared_text, replacements = prepare_text_for_translation(segment.text, glossary)
                prepared_texts.append(prepared_text)
                replacements_per_text.append(replacements)
            translated_texts = translate_batch_google(translator, prepared_texts)
            for segment, text, replacements in zip(batch, translated_texts, replacements_per_text):
                text = restore_translation_text(text, replacements)
                built_segments = build_display_friendly_subtitles(
                    segment,
                    text=text,
                    wrap_width=wrap_width,
                    start_index=next_index,
                )
                translated.extend(built_segments)
                next_index += len(built_segments)
            print(f"Translated {min(offset + batch_size, len(segments))}/{len(segments)} groups", flush=True)
            time.sleep(0.4)
        return translated
