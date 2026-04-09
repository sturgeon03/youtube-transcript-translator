from __future__ import annotations

from pathlib import Path

from ..normalize.text_cleaner import normalize_text
from ..postprocess.quality_checks import QualityIssue
from ..transcript.models import TranscriptSegment


def write_bilingual_review_markdown(
    path: Path,
    english_segments: list[TranscriptSegment],
    korean_segments: list[TranscriptSegment],
    *,
    quality_issues: list[QualityIssue] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    issue_map: dict[int, list[QualityIssue]] = {}
    for issue in quality_issues or []:
        issue_map.setdefault(issue.segment_index, []).append(issue)

    lines = ["# EN/KR Review Output", ""]
    for english, korean in zip(english_segments, korean_segments):
        lines.append(f"## {english.index}")
        lines.append(f"- Time: `{english.start}` -> `{english.end}`")
        lines.append(f"- EN: {normalize_text(english.text)}")
        lines.append(f"- KO: {normalize_text(korean.text)}")
        for issue in issue_map.get(english.index, []):
            lines.append(f"- Warning [{issue.category}]: {issue.message}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8-sig")
