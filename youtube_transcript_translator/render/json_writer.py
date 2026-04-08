from __future__ import annotations

import json
from pathlib import Path

from ..transcript.models import TranscriptSegment


def write_segments_json(path: Path, segments: list[TranscriptSegment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "index": segment.index,
            "start_seconds": segment.start.total_seconds(),
            "end_seconds": segment.end.total_seconds(),
            "text": segment.text,
            "source": segment.source,
            "metadata": segment.metadata,
        }
        for segment in segments
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
