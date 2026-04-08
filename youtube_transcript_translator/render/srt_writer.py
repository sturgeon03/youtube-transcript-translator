from __future__ import annotations

from pathlib import Path

import srt

from ..transcript.models import TranscriptSegment, to_srt_subtitles


def write_srt(path: Path, segments: list[TranscriptSegment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(srt.compose(to_srt_subtitles(segments)), encoding="utf-8-sig")
