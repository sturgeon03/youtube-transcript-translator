from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable

import srt


@dataclass
class TranscriptSegment:
    index: int
    start: timedelta
    end: timedelta
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.text

    @content.setter
    def content(self, value: str) -> None:
        self.text = value

    def with_index(self, index: int) -> "TranscriptSegment":
        return TranscriptSegment(
            index=index,
            start=self.start,
            end=self.end,
            text=self.text,
            source=self.source,
            metadata=dict(self.metadata),
        )


@dataclass
class TranslationBatch:
    items: list[TranscriptSegment]
    batch_index: int = 0


@dataclass
class RenderedSubtitle:
    items: list[TranscriptSegment]
    format: str = "srt"


def from_srt_subtitle(subtitle: srt.Subtitle, *, source: str = "") -> TranscriptSegment:
    return TranscriptSegment(
        index=subtitle.index,
        start=subtitle.start,
        end=subtitle.end,
        text=subtitle.content,
        source=source,
    )


def from_srt_subtitles(subtitles: Iterable[srt.Subtitle], *, source: str = "") -> list[TranscriptSegment]:
    return [from_srt_subtitle(subtitle, source=source) for subtitle in subtitles]


def to_srt_subtitle(segment: TranscriptSegment) -> srt.Subtitle:
    return srt.Subtitle(
        index=segment.index,
        start=segment.start,
        end=segment.end,
        content=segment.text,
    )


def to_srt_subtitles(segments: Iterable[TranscriptSegment]) -> list[srt.Subtitle]:
    return [to_srt_subtitle(segment) for segment in segments]
