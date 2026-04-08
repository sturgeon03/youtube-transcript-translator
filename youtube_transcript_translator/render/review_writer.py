from __future__ import annotations

from pathlib import Path

from ..normalize.text_cleaner import normalize_text
from ..transcript.models import TranscriptSegment


def write_bilingual_review_markdown(
    path: Path,
    english_segments: list[TranscriptSegment],
    korean_segments: list[TranscriptSegment],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# EN/KR Review Output", ""]
    for english, korean in zip(english_segments, korean_segments):
        lines.append(f"## {english.index}")
        lines.append(f"- Time: `{english.start}` -> `{english.end}`")
        lines.append(f"- EN: {normalize_text(english.text)}")
        lines.append(f"- KO: {normalize_text(korean.text)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8-sig")
