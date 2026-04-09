from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..glossary.loader import load_glossary
from ..normalize.regroup import build_display_friendly_subtitles, regroup_subtitles
from ..overlay_registry import register_subtitle
from ..postprocess.quality_checks import QualityIssue, collect_translation_quality_issues
from ..render.json_writer import write_segments_json
from ..render.review_writer import write_bilingual_review_markdown
from ..render.srt_writer import write_srt
from ..sources.local_files import load_subtitles
from ..sources.youtube import extract_video_id
from ..transcript.models import TranscriptSegment
from ..transcript.providers import resolve_transcript_from_url, write_english_outputs
from ..translation import translate_segments
from .config import PipelineConfig


@dataclass
class PipelineResult:
    input_reference: Path
    english_segments_count: int
    grouped_segments_count: int
    korean_output_path: Path
    quality_issue_count: int = 0
    overlay_subtitle_path: Path | None = None


def default_output_path(input_reference: Path) -> Path:
    name = input_reference.name
    if name.endswith(".en.srt"):
        return input_reference.with_name(name.replace(".en.srt", ".ko.grouped.srt"))
    return input_reference.with_suffix(".ko.grouped.srt")


def build_display_segments(
    translated_groups: list[TranscriptSegment],
    *,
    wrap_width: int,
) -> list[TranscriptSegment]:
    display_segments: list[TranscriptSegment] = []
    next_index = 1
    for segment in translated_groups:
        built = build_display_friendly_subtitles(
            segment,
            text=segment.text,
            wrap_width=wrap_width,
            start_index=next_index,
        )
        display_segments.extend(built)
        next_index += len(built)
    return display_segments


def report_quality_issues(issues: list[QualityIssue]) -> None:
    if not issues:
        return

    category_counts: dict[str, int] = {}
    for issue in issues:
        category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
    summary = ", ".join(f"{category}={count}" for category, count in sorted(category_counts.items()))
    print(f"Quality warnings: {len(issues)} ({summary})", flush=True)


def run_pipeline(config: PipelineConfig, *, target_dir: Path | None = None) -> PipelineResult:
    target_dir = target_dir or Path.cwd()
    glossary = load_glossary(
        config.translation.glossary_path,
        glossary_profile=config.translation.glossary_profile,
        registry_path=config.translation.glossary_registry_path,
    )

    if config.input_path is not None:
        input_reference = config.input_path.resolve()
        english_segments = load_subtitles(input_reference)
        if config.output.english_text_output is not None:
            write_english_outputs(
                english_segments,
                srt_path=config.output.english_output.resolve() if config.output.english_output else None,
                text_path=config.output.english_text_output.resolve(),
            )
        elif config.output.english_output is not None:
            write_english_outputs(
                english_segments,
                srt_path=config.output.english_output.resolve(),
                text_path=None,
            )
    elif config.url:
        english_segments, input_reference = resolve_transcript_from_url(
            config.url,
            target_dir=target_dir,
            transcript_source=config.transcript.source_mode,
            transcription_language=config.transcript.language,
            local_transcription_model=config.transcript.local_model,
            local_transcription_device=config.transcript.local_device,
            local_transcription_compute_type=config.transcript.local_compute_type,
            english_output=config.output.english_output,
            english_text_output=config.output.english_text_output,
        )
    else:
        raise ValueError("No input subtitle source was resolved.")

    output_path = config.output.output_path.resolve() if config.output.output_path else default_output_path(input_reference)
    grouped_segments = regroup_subtitles(
        english_segments,
        max_group_seconds=config.max_group_seconds,
        max_group_words=config.max_group_words,
        max_gap_seconds=config.max_gap_seconds,
    )
    translated_groups = translate_segments(
        grouped_segments,
        config=config.translation,
        glossary=glossary,
    )
    quality_issues = collect_translation_quality_issues(
        grouped_segments,
        translated_groups,
        glossary=glossary,
        wrap_width=config.translation.wrap_width,
    )
    report_quality_issues(quality_issues)

    display_segments = build_display_segments(
        translated_groups,
        wrap_width=config.translation.wrap_width,
    )
    write_srt(output_path, display_segments)

    if config.output.review_output is not None:
        write_bilingual_review_markdown(
            config.output.review_output.resolve(),
            grouped_segments,
            translated_groups,
            quality_issues=quality_issues,
        )
    if config.output.json_output is not None:
        write_segments_json(config.output.json_output.resolve(), translated_groups)

    registered_overlay_path: Path | None = None
    if config.output.extension_root is not None:
        registration_video_id = config.output.video_id or (extract_video_id(config.url) if config.url else None)
        if not registration_video_id:
            raise ValueError("--extension-root requires --video-id when the input is not a YouTube URL.")
        registered_overlay_path = register_subtitle(
            config.output.extension_root.resolve(),
            registration_video_id,
            output_path,
            label=config.output.overlay_label,
        )

    return PipelineResult(
        input_reference=input_reference,
        english_segments_count=len(english_segments),
        grouped_segments_count=len(grouped_segments),
        korean_output_path=output_path,
        quality_issue_count=len(quality_issues),
        overlay_subtitle_path=registered_overlay_path,
    )
