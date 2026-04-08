from __future__ import annotations

from pathlib import Path

from ..sources.local_files import load_subtitles
from ..sources.youtube import try_download_english_auto_subtitles
from .models import TranscriptSegment


def resolve_youtube_english_subtitles(url: str, target_dir: Path) -> tuple[list[TranscriptSegment], Path] | None:
    subtitle_path = try_download_english_auto_subtitles(url, target_dir)
    if subtitle_path is None:
        return None
    subtitles = load_subtitles(subtitle_path)
    return subtitles, subtitle_path.resolve()
