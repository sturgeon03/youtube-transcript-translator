from __future__ import annotations

from abc import ABC, abstractmethod

from ..transcript.models import TranscriptSegment


class TranslationBackend(ABC):
    name: str

    @abstractmethod
    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        batch_size: int,
        glossary: dict[str, str],
    ) -> list[TranscriptSegment]:
        raise NotImplementedError
