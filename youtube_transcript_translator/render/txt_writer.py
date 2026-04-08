from __future__ import annotations

from pathlib import Path

from ..normalize.text_cleaner import normalize_text
from ..transcript.models import TranscriptSegment


def subtitles_to_plain_text(subtitles: list[TranscriptSegment]) -> str:
    lines = []
    for subtitle in subtitles:
        text = normalize_text(subtitle.text)
        if text:
            lines.append(text)
    return "\n".join(lines)


def write_plain_text(path: Path, subtitles: list[TranscriptSegment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(subtitles_to_plain_text(subtitles), encoding="utf-8-sig")
