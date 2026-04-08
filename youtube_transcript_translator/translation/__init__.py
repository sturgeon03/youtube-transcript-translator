from __future__ import annotations

from ..app.config import TranslationConfig
from ..transcript.models import TranscriptSegment
from .base import TranslationBackend
from .google_backend import GoogleTranslationBackend
from .openai_backend import OpenAITranslationBackend


def get_translation_backend(config: TranslationConfig) -> TranslationBackend:
    if config.backend == "openai":
        return OpenAITranslationBackend(
            model=config.openai_model,
            reasoning_effort=config.openai_reasoning_effort,
            api_key_env=config.openai_api_key_env,
            timeout_seconds=config.openai_timeout_seconds,
        )
    return GoogleTranslationBackend()


def translate_segments(
    segments: list[TranscriptSegment],
    *,
    config: TranslationConfig,
    glossary: dict[str, str],
) -> list[TranscriptSegment]:
    backend = get_translation_backend(config)
    return backend.translate_segments(
        segments,
        wrap_width=config.wrap_width,
        batch_size=config.batch_size,
        glossary=glossary,
    )
