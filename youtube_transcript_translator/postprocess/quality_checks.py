from __future__ import annotations

from ..normalize.regroup import wrapped_lines
from ..transcript.models import TranscriptSegment


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
