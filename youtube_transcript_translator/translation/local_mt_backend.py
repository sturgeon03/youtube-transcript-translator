from __future__ import annotations

from ..transcript.models import TranscriptSegment
from .base import TranslationBackend


class LocalMTTranslationBackend(TranslationBackend):
    name = "local_mt"

    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        wrap_width: int,
        batch_size: int,
        glossary: dict[str, str],
    ) -> list[TranscriptSegment]:
        raise NotImplementedError("Local machine translation backend is not implemented yet.")
