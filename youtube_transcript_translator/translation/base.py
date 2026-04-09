from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from ..transcript.models import TranscriptSegment


class ProgressCallback(Protocol):
    def __call__(
        self,
        *,
        stage: str,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None: ...


def report_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage: str,
    progress: float | None = None,
    detail: str | None = None,
) -> None:
    if progress_callback is None:
        return
    progress_callback(stage=stage, progress=progress, detail=detail)


class TranslationBackend(ABC):
    name: str

    @abstractmethod
    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        batch_size: int,
        glossary: dict[str, str],
        progress_callback: ProgressCallback | None = None,
    ) -> list[TranscriptSegment]:
        raise NotImplementedError
