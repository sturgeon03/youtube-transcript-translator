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
from ..translation.base import ProgressCallback, report_progress
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


def run_pipeline(
    config: PipelineConfig,
    *,
    target_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    target_dir = target_dir or Path.cwd()
    report_progress(
        progress_callback,
        stage="loading_glossary",
        progress=3.0,
        detail="Loading glossary rules",
    )
    glossary = load_glossary(
        config.translation.glossary_path,
        glossary_profile=config.translation.glossary_profile,
        registry_path=config.translation.glossary_registry_path,
    )
    report_progress(
        progress_callback,
        stage="loading_glossary",
        progress=6.0,
        detail=f"Loaded {len(glossary)} glossary entries",
    )

    if config.input_path is not None:
        report_progress(
            progress_callback,
            stage="loading_input",
            progress=12.0,
            detail="Loading local English subtitle input",
        )
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
        report_progress(
            progress_callback,
            stage="resolving_transcript",
            progress=12.0,
            detail="Resolving English transcript from YouTube",
        )

        def transcript_progress(
            *,
            stage: str,
            progress: float | None = None,
            detail: str | None = None,
        ) -> None:
            mapped_progress = 12.0
            if progress is not None:
                mapped_progress = 12.0 + max(0.0, min(100.0, progress)) * 0.16
            report_progress(
                progress_callback,
                stage=stage,
                progress=mapped_progress,
                detail=detail,
            )

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
            progress_callback=transcript_progress,
        )
    else:
        raise ValueError("No input subtitle source was resolved.")

    report_progress(
        progress_callback,
        stage="english_ready",
        progress=28.0,
        detail=f"Resolved {len(english_segments)} English subtitle segments",
    )
    output_path = config.output.output_path.resolve() if config.output.output_path else default_output_path(input_reference)
    report_progress(
        progress_callback,
        stage="grouping_subtitles",
        progress=32.0,
        detail="Grouping English transcript into translation units",
    )
    grouped_segments = regroup_subtitles(
        english_segments,
        max_group_seconds=config.max_group_seconds,
        max_group_words=config.max_group_words,
        max_gap_seconds=config.max_gap_seconds,
    )
    report_progress(
        progress_callback,
        stage="grouping_subtitles",
        progress=38.0,
        detail=f"Prepared {len(grouped_segments)} translation groups",
    )

    def translation_progress(
        *,
        stage: str,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None:
        mapped_progress = 38.0
        if progress is not None:
            mapped_progress = 38.0 + max(0.0, min(100.0, progress)) * 0.48
        report_progress(
            progress_callback,
            stage=stage,
            progress=mapped_progress,
            detail=detail,
        )

    translated_groups = translate_segments(
        grouped_segments,
        config=config.translation,
        glossary=glossary,
        progress_callback=translation_progress,
    )
    report_progress(
        progress_callback,
        stage="quality_checks",
        progress=88.0,
        detail="Running translation quality checks",
    )
    quality_issues = collect_translation_quality_issues(
        grouped_segments,
        translated_groups,
        glossary=glossary,
        wrap_width=config.translation.wrap_width,
    )
    report_quality_issues(quality_issues)

    report_progress(
        progress_callback,
        stage="rendering_subtitles",
        progress=93.0,
        detail="Formatting display-friendly Korean subtitles",
    )
    display_segments = build_display_segments(
        translated_groups,
        wrap_width=config.translation.wrap_width,
    )
    write_srt(output_path, display_segments)

    if config.output.review_output is not None:
        report_progress(
            progress_callback,
            stage="writing_artifacts",
            progress=95.0,
            detail="Writing bilingual review output",
        )
        write_bilingual_review_markdown(
            config.output.review_output.resolve(),
            grouped_segments,
            translated_groups,
            quality_issues=quality_issues,
        )
    if config.output.json_output is not None:
        report_progress(
            progress_callback,
            stage="writing_artifacts",
            progress=97.0,
            detail="Writing machine-readable segment artifact",
        )
        write_segments_json(config.output.json_output.resolve(), translated_groups)

    registered_overlay_path: Path | None = None
    if config.output.extension_root is not None:
        report_progress(
            progress_callback,
            stage="registering_overlay",
            progress=99.0,
            detail="Registering generated subtitles with the Chrome overlay",
        )
        registration_video_id = config.output.video_id or (extract_video_id(config.url) if config.url else None)
        if not registration_video_id:
            raise ValueError("--extension-root requires --video-id when the input is not a YouTube URL.")
        registered_overlay_path = register_subtitle(
            config.output.extension_root.resolve(),
            registration_video_id,
            output_path,
            label=config.output.overlay_label,
        )

    report_progress(
        progress_callback,
        stage="completed",
        progress=100.0,
        detail="Pipeline completed",
    )

    return PipelineResult(
        input_reference=input_reference,
        english_segments_count=len(english_segments),
        grouped_segments_count=len(grouped_segments),
        korean_output_path=output_path,
        quality_issue_count=len(quality_issues),
        overlay_subtitle_path=registered_overlay_path,
    )
