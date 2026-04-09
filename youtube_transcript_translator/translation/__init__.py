from __future__ import annotations

from ..app.config import TranslationConfig
from ..transcript.models import TranscriptSegment
from .base import ProgressCallback, TranslationBackend
from .google_backend import GoogleTranslationBackend
from .local_mt_backend import LocalMTTranslationBackend


def get_translation_backend(config: TranslationConfig) -> TranslationBackend:
    if config.backend == "google":
        return GoogleTranslationBackend()
    if config.backend == "local_mt":
        return LocalMTTranslationBackend(
            model_name=config.local_model,
            device=config.local_device,
            source_lang=config.local_source_lang,
            target_lang=config.local_target_lang,
            max_input_length=config.local_max_input_length,
            max_new_tokens=config.local_max_new_tokens,
            num_beams=config.local_num_beams,
        )
    raise ValueError(f"Unsupported translation backend: {config.backend}")


def translate_segments(
    segments: list[TranscriptSegment],
    *,
    config: TranslationConfig,
    glossary: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> list[TranscriptSegment]:
    backend = get_translation_backend(config)
    return backend.translate_segments(
        segments,
        batch_size=config.batch_size,
        glossary=glossary,
        progress_callback=progress_callback,
    )
